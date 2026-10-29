#!/usr/bin/env python3
"""Create a verified, non-destructive backup for a reviewed delete set.

Reads a TSV containing branch, sha, why, worktree, dirty_files, and reason.
Candidates whose refs moved are excluded. Dirty worktree edits are preserved,
and every surviving branch tip is stored in a verified Git bundle.

This script never deletes refs or worktrees.

Usage: backup.py --repo REPO --delete-set delete-set.tsv --backup-dir DIR
"""

from __future__ import annotations

import argparse
import csv
import re
import subprocess
import sys
import tarfile
from dataclasses import dataclass
from pathlib import Path

SHA_RE = re.compile(r"[0-9a-f]{40}")
TSV_COLUMNS = ("branch", "sha", "why", "worktree", "dirty_files", "reason")

RESTORE_MD = """\
# Restoring from this backup

## Restore a deleted branch

    git fetch {bundle} refs/heads/<branch>:refs/heads/<branch>

## Reapply a dirty worktree's uncommitted edits

Each `worktree-edits/<sanitized-branch>-<sha>/` directory contains the
uncommitted state saved at backup time:

    git apply worktree-edits/<branch>/tracked.patch
    tar xzf worktree-edits/<branch>/untracked.tar.gz

The tar command is needed only when `untracked.tar.gz` exists. `meta.txt`
records the original worktree path and reviewed branch head.
"""


@dataclass(slots=True)
class Git:
    root: Path

    def run(
        self, *args: str, cwd: Path | None = None, check: bool = True
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args],
            cwd=cwd or self.root,
            text=True,
            capture_output=True,
            check=check,
            encoding="utf-8",
            errors="replace",
        )

    def out(self, *args: str, cwd: Path | None = None, check: bool = True) -> str:
        return self.run(*args, cwd=cwd, check=check).stdout.strip()


@dataclass(slots=True)
class DeleteRow:
    branch: str
    sha: str
    why: str
    worktree: str
    dirty_files: str
    reason: str

    def as_tsv(self) -> list[str]:
        return [
            self.branch,
            self.sha,
            self.why,
            self.worktree,
            self.dirty_files,
            self.reason,
        ]


def repo_root(repo: str) -> Path:
    """Resolve and validate the repository root."""
    result = subprocess.run(
        ["git", "-C", repo, "rev-parse", "--show-toplevel"],
        text=True,
        capture_output=True,
        check=True,
        encoding="utf-8",
        errors="replace",
    )
    return Path(result.stdout.strip())


def parse_dirty_files(value: str, branch: str) -> int:
    """Require a known non-negative triage-time dirty-file count."""
    if value == "":
        raise ValueError(f"missing dirty_files for {branch!r}")
    try:
        count = int(value)
    except ValueError as exc:
        raise ValueError(f"invalid dirty_files for {branch!r}: {value!r}") from exc
    if count < 0:
        raise ValueError(
            f"unknown/negative dirty_files is not cleanup-safe for {branch!r}: {count}"
        )
    return count


def read_delete_set(path: Path) -> list[DeleteRow]:
    """Read and strictly validate the reviewed delete-set TSV."""
    if not path.is_file():
        raise FileNotFoundError(path)

    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if tuple(reader.fieldnames or ()) != TSV_COLUMNS:
            raise ValueError(
                f"delete-set columns must be exactly {TSV_COLUMNS}, got {reader.fieldnames}"
            )

        rows: list[DeleteRow] = []
        seen: set[str] = set()
        for line_number, raw in enumerate(reader, start=2):
            row = DeleteRow(*(raw[column] or "" for column in TSV_COLUMNS))
            if not row.branch:
                raise ValueError(f"line {line_number}: empty branch")
            if row.branch in seen:
                raise ValueError(f"line {line_number}: duplicate branch {row.branch!r}")
            if not SHA_RE.fullmatch(row.sha):
                raise ValueError(f"line {line_number}: invalid SHA for {row.branch!r}")
            parse_dirty_files(row.dirty_files, row.branch)
            rows.append(row)
            seen.add(row.branch)

    return rows


def split_moved_refs(
    git: Git, rows: list[DeleteRow]
) -> tuple[list[DeleteRow], list[DeleteRow]]:
    """Keep only rows whose local branch still points at the reviewed SHA."""
    valid: list[DeleteRow] = []
    moved: list[DeleteRow] = []

    for row in rows:
        current = git.out(
            "rev-parse", "--verify", "-q", f"refs/heads/{row.branch}", check=False
        )
        (valid if current == row.sha else moved).append(row)

    return valid, moved


def validate_worktree_identity(git: Git, row: DeleteRow) -> None:
    """Ensure a recorded worktree still exists at the reviewed branch head."""
    if not row.worktree:
        if parse_dirty_files(row.dirty_files, row.branch) > 0:
            raise RuntimeError(
                f"{row.branch}: dirty state was recorded without a worktree path"
            )
        return

    worktree = Path(row.worktree)
    if not worktree.exists():
        raise RuntimeError(f"{row.branch}: recorded worktree disappeared: {worktree}")

    head = git.out("rev-parse", "HEAD", cwd=worktree)
    if head != row.sha:
        raise RuntimeError(
            f"{row.branch}: worktree HEAD changed after review ({row.sha} -> {head})"
        )


def untracked_paths(git: Git, worktree: Path) -> list[str]:
    """Return untracked paths safely using NUL-delimited Git output."""
    result = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard", "-z"],
        cwd=worktree,
        capture_output=True,
        check=True,
    )
    return [
        item.decode("utf-8", errors="surrogateescape")
        for item in result.stdout.split(b"\0")
        if item
    ]


def save_worktree_edits(git: Git, row: DeleteRow, backup_dir: Path) -> bool:
    """Validate and save dirty worktree state before cleanup."""
    expected_dirty = parse_dirty_files(row.dirty_files, row.branch)
    if not row.worktree:
        return False

    worktree = Path(row.worktree)
    status = git.run("status", "--porcelain", cwd=worktree, check=False)
    if status.returncode != 0:
        raise RuntimeError(
            f"{row.branch}: cannot read worktree status: "
            f"{status.stderr.strip() or status.returncode}"
        )

    current_dirty = len(status.stdout.splitlines())
    if current_dirty != expected_dirty:
        raise RuntimeError(
            f"{row.branch}: worktree changed after triage "
            f"(dirty files {expected_dirty} -> {current_dirty}); re-triage before cleanup"
        )
    if current_dirty == 0:
        return False

    dest = (
        backup_dir
        / "worktree-edits"
        / f"{row.branch.replace('/', '__')}-{row.sha[:12]}"
    )
    dest.mkdir(parents=True, exist_ok=True)

    tracked_patch = subprocess.run(
        ["git", "diff", "HEAD", "--binary"],
        cwd=worktree,
        capture_output=True,
        check=True,
    ).stdout
    (dest / "tracked.patch").write_bytes(tracked_patch)

    untracked = untracked_paths(git, worktree)
    if untracked:
        with tarfile.open(dest / "untracked.tar.gz", "w:gz") as archive:
            for relative in untracked:
                path = worktree / relative
                if not path.exists() and not path.is_symlink():
                    raise RuntimeError(
                        f"{row.branch}: untracked path disappeared during backup: {relative}"
                    )
                archive.add(path, arcname=relative, recursive=True)

    (dest / "meta.txt").write_text(
        f"worktree: {worktree}\nbranch: {row.branch}\nhead: {row.sha}\n",
        encoding="utf-8",
    )
    return True


def bundle_branches(git: Git, rows: list[DeleteRow], bundle_path: Path) -> int:
    """Create and verify a bundle containing every surviving reviewed branch."""
    refs = "".join(f"refs/heads/{row.branch}\n" for row in rows)
    subprocess.run(
        ["git", "bundle", "create", str(bundle_path), "--stdin"],
        cwd=git.root,
        input=refs,
        text=True,
        check=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )
    git.run("bundle", "verify", str(bundle_path))
    heads = git.out("bundle", "list-heads", str(bundle_path)).splitlines()
    return len(heads)


def write_tsv(path: Path, rows: list[DeleteRow]) -> None:
    """Write a normalized delete-set TSV."""
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, delimiter="\t")
        writer.writerow(TSV_COLUMNS)
        writer.writerows(row.as_tsv() for row in rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--repo", required=True)
    parser.add_argument("--delete-set", required=True, type=Path)
    parser.add_argument("--backup-dir", required=True, type=Path)
    args = parser.parse_args()

    git = Git(repo_root(args.repo))
    backup_dir = args.backup_dir.resolve()
    backup_dir.mkdir(parents=True, exist_ok=True)

    rows = read_delete_set(args.delete_set)
    if not rows:
        print("ok=0 dropped=0 edits_saved=0 bundle_heads=0 (empty delete set)")
        return 0

    valid, moved = split_moved_refs(git, rows)
    if moved:
        write_tsv(backup_dir / "delete-dropped.tsv", moved)
    if not valid:
        raise RuntimeError("every candidate branch changed or disappeared; re-triage")

    for row in valid:
        validate_worktree_identity(git, row)

    saved = sum(save_worktree_edits(git, row, backup_dir) for row in valid)
    expected_saved = sum(
        parse_dirty_files(row.dirty_files, row.branch) > 0 for row in valid
    )
    if saved != expected_saved:
        raise AssertionError(
            f"dirty worktree backup mismatch: saved {saved} != expected {expected_saved}"
        )

    bundle_path = backup_dir / "branches.bundle"
    heads = bundle_branches(git, valid, bundle_path)
    if heads != len(valid):
        raise AssertionError(f"bundle head count mismatch: {heads} != {len(valid)}")

    write_tsv(backup_dir / "branches-backed-up.tsv", valid)
    write_tsv(args.delete_set.parent / "delete-ok.tsv", valid)
    (backup_dir / "RESTORE.md").write_text(
        RESTORE_MD.format(bundle=bundle_path), encoding="utf-8"
    )

    print(
        f"ok={len(valid)} dropped={len(moved)} {[row.branch for row in moved]} "
        f"edits_saved={saved} bundle_heads={heads}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
