#!/usr/bin/env python3
"""Read-only residual-work report for unresolved branches/worktrees.

Takes inventory.py's JSON output and measures whether orphan-branch content
already exists in the pinned base commit by line, not just by file overlap.
`landed_ratio` is a triage heuristic, never deletion proof. Missing/unknown
worktree state is surfaced as unresolved rather than treated as clean.

Never writes refs, the index, or working-tree files. `git merge-tree --write-tree`
may create unreachable Git objects while computing merge results.

Usage: residual.py INVENTORY.json [--out FILE]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path

WORKERS = 16
COMMIT_SUBJECT_LIMIT = 15
RESIDUAL_PATH_LIMIT = 40
GREP_SAMPLE_LIMIT = 200
MISSING_SAMPLE_LIMIT = 8
MIN_LINE_LENGTH = 12
SUPERSEDED_RATIO = 0.9
SUPERSEDED_MAX_MISSING_LINES = 50
MOSTLY_LANDED_RATIO = 0.6
TINY_MISSING_LINE_LIMIT = 20

NOISE_PATH_MARKERS = (
    ".terraform.lock.hcl",
    "node_modules/",
    ".DS_Store",
    "/dist/",
    "/bin/",
    "/.venv/",
    "__pycache__",
)


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
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=check,
        )

    def out(self, *args: str, cwd: Path | None = None, check: bool = False) -> str:
        return self.run(*args, cwd=cwd, check=check).stdout.strip()

    def exists(self, ref: str, path: str) -> bool:
        return self.run("cat-file", "-e", f"{ref}:{path}", check=False).returncode == 0


@dataclass(slots=True)
class NumstatTotal:
    files: int = 0
    added: int = 0
    removed: int = 0
    paths: list[str] = field(default_factory=list)


@dataclass(slots=True)
class Uncommitted:
    files: int
    added: int
    removed: int
    untracked_count: int
    paths: list[str]
    noise_paths: list[str]
    hint: str = ""


@dataclass(slots=True)
class MissingLine:
    path: str
    line: str


@dataclass(slots=True)
class ResidualTarget:
    name: str
    sha: str
    kind: str
    worktree_state: str = "none"
    hint: str = ""
    conflicts: bool = False
    conflicted_paths: list[str] = field(default_factory=list)
    residual_is_approx: bool = False
    files_changed: int = 0
    lines_added: int = 0
    lines_removed: int = 0
    paths: list[str] = field(default_factory=list)
    dirs_touched: list[str] = field(default_factory=list)
    lines_considered: int = 0
    lines_missing: int = 0
    landed_ratio: float | None = None
    missing_sample: list[MissingLine] = field(default_factory=list)
    commit_subjects: list[str] = field(default_factory=list)
    uncommitted: Uncommitted | None = None


class BaseContentCache:
    """Cache pinned-base file contents and path-existence checks."""

    def __init__(self, git: Git, base: str) -> None:
        self._git = git
        self._base = base
        self._lock = threading.Lock()
        self._exists: dict[str, bool] = {}
        self._stripped_lines: dict[str, frozenset[str]] = {}

    def exists(self, path: str) -> bool:
        with self._lock:
            cached = self._exists.get(path)
        if cached is not None:
            return cached

        result = self._git.exists(self._base, path)
        with self._lock:
            self._exists[path] = result
        return result

    def stripped_lines(self, path: str) -> frozenset[str]:
        with self._lock:
            cached = self._stripped_lines.get(path)
        if cached is not None:
            return cached

        content = self._git.out("show", f"{self._base}:{path}")
        lines = frozenset(line.strip() for line in content.splitlines())
        with self._lock:
            self._stripped_lines[path] = lines
        return lines


def is_noise(path: str) -> bool:
    return any(marker in path for marker in NOISE_PATH_MARKERS)


def is_distinctive(stripped: str) -> bool:
    """Return whether a line is useful enough for content-presence comparison."""
    return len(stripped) >= MIN_LINE_LENGTH and any(char.isalnum() for char in stripped)


def parse_numstat(text: str) -> NumstatTotal:
    total = NumstatTotal()
    for line in text.splitlines():
        parts = line.split("\t", 2)
        if len(parts) != 3:
            continue
        added, removed, path = parts
        total.files += 1
        total.added += int(added) if added.isdigit() else 0
        total.removed += int(removed) if removed.isdigit() else 0
        total.paths.append(path)
    return total


def top_level_dirs(paths: list[str]) -> list[str]:
    """Return conservative grep scopes for moved/deleted-path searches."""
    dirs = {path.split("/", 1)[0] if "/" in path else "." for path in paths}
    return sorted(dirs)


def merge_conflicts(git: Git, base: str, sha: str) -> tuple[bool, list[str], str]:
    """Return (conflicts, conflicted_paths, merged_tree_or_empty)."""
    result = git.run(
        "merge-tree", "--write-tree", "--name-only", base, sha, check=False
    )
    if result.returncode == 0:
        tokens = result.stdout.split()
        return False, [], tokens[0] if tokens else ""
    if result.returncode == 1:
        block = result.stdout.split("\n\n", 1)[0]
        return True, [path for path in block.splitlines() if path], ""
    return True, [], ""


def commit_subjects(git: Git, base: str, sha: str) -> list[str]:
    output = git.out("log", "--format=%s", f"{base}..{sha}")
    return output.splitlines()[:COMMIT_SUBJECT_LIMIT] if output else []


@dataclass(slots=True)
class DiffLines:
    """Distinctive added/deleted lines from a unified diff, grouped by path."""

    added_by_path: dict[str, list[str]] = field(default_factory=dict)
    deleted_by_path: dict[str, list[str]] = field(default_factory=dict)


def parse_unified_diff(text: str) -> DiffLines:
    """Group distinctive added/deleted lines by non-noise path."""
    result = DiffLines()
    add_path = del_path = None

    for line in text.splitlines():
        if line.startswith("+++ "):
            target = line[4:]
            add_path = (
                None
                if target == "/dev/null" or is_noise(target)
                else target.removeprefix("b/")
            )
            continue
        if line.startswith("--- "):
            target = line[4:]
            del_path = (
                None
                if target == "/dev/null" or is_noise(target)
                else target.removeprefix("a/")
            )
            continue
        if line.startswith(("+++", "---")):
            continue
        if line.startswith("+") and add_path:
            stripped = line[1:].strip()
            if is_distinctive(stripped):
                result.added_by_path.setdefault(add_path, []).append(stripped)
        elif line.startswith("-") and del_path:
            stripped = line[1:].strip()
            if is_distinctive(stripped):
                result.deleted_by_path.setdefault(del_path, []).append(stripped)

    return result


def grep_present(
    git: Git, base: str, lines: list[str], search_dirs: list[str], tmp_dir: Path
) -> set[str]:
    """Return which exact lines appear in the pinned base within scoped paths."""
    if not lines or not search_dirs:
        return set()

    with tempfile.NamedTemporaryFile(
        "w",
        dir=tmp_dir,
        prefix="residual-grep-",
        suffix=".txt",
        delete=True,
        encoding="utf-8",
    ) as pattern_file:
        pattern_file.write("\n".join(lines))
        pattern_file.flush()
        result = git.run(
            "grep",
            "-F",
            "-x",
            "-f",
            pattern_file.name,
            base,
            "--",
            *search_dirs,
            check=False,
        )

    if result.returncode not in (0, 1):
        return set()

    matched: set[str] = set()
    for output_line in result.stdout.splitlines():
        _, _, content = output_line.partition(":")
        # `git grep <tree>` emits <tree>:<path>:<content>; split once more.
        _, _, content = content.partition(":")
        if content:
            matched.add(content)
    return matched.intersection(lines)


def landed_ratio_for_added_lines(
    git: Git,
    base: str,
    cache: BaseContentCache,
    diff: DiffLines,
    tmp_dir: Path,
) -> tuple[int, int, list[MissingLine], bool]:
    considered = 0
    present = 0
    missing: list[MissingLine] = []
    gone_candidates: dict[str, str] = {}

    for path, added_lines in diff.added_by_path.items():
        if cache.exists(path):
            base_lines = cache.stripped_lines(path)
            for stripped in added_lines:
                considered += 1
                if stripped in base_lines:
                    present += 1
                elif len(missing) < MISSING_SAMPLE_LIMIT:
                    missing.append(MissingLine(path, stripped))
        else:
            for stripped in added_lines:
                gone_candidates.setdefault(stripped, path)

    sampled = list(gone_candidates.items())[:GREP_SAMPLE_LIMIT]
    approximate = len(gone_candidates) > GREP_SAMPLE_LIMIT
    search_dirs = top_level_dirs([path for _, path in sampled])
    found = grep_present(git, base, [line for line, _ in sampled], search_dirs, tmp_dir)

    for stripped, path in sampled:
        considered += 1
        if stripped in found:
            present += 1
        elif len(missing) < MISSING_SAMPLE_LIMIT:
            missing.append(MissingLine(path, stripped))

    return considered, present, missing, approximate


def landed_ratio_for_deletion_only(
    cache: BaseContentCache, diff: DiffLines
) -> tuple[int, int, list[MissingLine]]:
    """Treat a deletion as landed when the base also lacks the deleted line."""
    considered = 0
    present = 0
    missing: list[MissingLine] = []

    for path, deleted_lines in diff.deleted_by_path.items():
        if not cache.exists(path):
            considered += len(deleted_lines)
            present += len(deleted_lines)
            continue

        base_lines = cache.stripped_lines(path)
        for stripped in deleted_lines:
            considered += 1
            if stripped not in base_lines:
                present += 1
            elif len(missing) < MISSING_SAMPLE_LIMIT:
                missing.append(MissingLine(path, stripped))

    return considered, present, missing


def measure_branch(
    git: Git,
    base: str,
    cache: BaseContentCache,
    branch: dict,
    tmp_dir: Path,
) -> ResidualTarget:
    sha = branch["sha"]
    target = ResidualTarget(
        name=branch["name"],
        sha=sha,
        kind="branch",
        worktree_state=branch.get("worktree_state", "none"),
    )
    target.commit_subjects = commit_subjects(git, base, sha)

    conflicts, conflicted_paths, merged_tree = merge_conflicts(git, base, sha)
    target.conflicts = conflicts
    target.conflicted_paths = conflicted_paths
    target.residual_is_approx = conflicts

    merge_base = git.out("merge-base", base, sha)
    if conflicts or not merged_tree:
        numstat = git.out("diff", "--numstat", merge_base, sha)
    else:
        numstat = git.out("diff", "--numstat", base, merged_tree)

    total = parse_numstat(numstat)
    target.files_changed = total.files
    target.lines_added = total.added
    target.lines_removed = total.removed
    target.paths = total.paths[:RESIDUAL_PATH_LIMIT]
    target.dirs_touched = top_level_dirs(total.paths)

    diff = parse_unified_diff(git.out("diff", merge_base, sha))
    has_additions = any(diff.added_by_path.values())

    if has_additions:
        considered, present, missing, approximate = landed_ratio_for_added_lines(
            git, base, cache, diff, tmp_dir
        )
        target.residual_is_approx = target.residual_is_approx or approximate
    elif any(diff.deleted_by_path.values()):
        considered, present, missing = landed_ratio_for_deletion_only(cache, diff)
    else:
        considered, present, missing = 0, 0, []

    target.lines_considered = considered
    target.lines_missing = considered - present
    target.landed_ratio = (present / considered) if considered else None
    target.missing_sample = missing
    return target


def measure_dirty_worktree(git: Git, branch: dict) -> Uncommitted:
    """Measure a worktree already proven dirty by inventory."""
    worktree = Path(branch["worktree"])
    if not worktree.exists():
        raise RuntimeError(f"dirty worktree disappeared: {worktree}")

    numstat = git.out("diff", "HEAD", "--numstat", cwd=worktree, check=True)
    total = parse_numstat(numstat)

    status = git.run("status", "--porcelain", cwd=worktree, check=False)
    if status.returncode != 0:
        raise RuntimeError(
            f"cannot read dirty worktree status for {branch['name']}: "
            f"{status.stderr.strip() or status.returncode}"
        )

    status_lines = status.stdout.splitlines()
    untracked = [line[3:] for line in status_lines if line.startswith("??")]
    all_paths = total.paths + untracked
    noise = [path for path in all_paths if is_noise(path)]
    real_paths = [path for path in all_paths if not is_noise(path)]

    uncommitted = Uncommitted(
        files=total.files,
        added=total.added,
        removed=total.removed,
        untracked_count=len(untracked),
        paths=real_paths[:RESIDUAL_PATH_LIMIT],
        noise_paths=noise[:RESIDUAL_PATH_LIMIT],
    )
    uncommitted.hint = "edits" if real_paths else "noise-only"
    return uncommitted


def classify_branch_hint(target: ResidualTarget) -> str:
    """Return a triage hint; never a deletion verdict."""
    if target.worktree_state in {"missing", "unknown"}:
        return "unknown"

    has_real_uncommitted = (
        bool(target.uncommitted) and target.uncommitted.hint == "edits"
    )

    if target.lines_considered == 0:
        if not has_real_uncommitted:
            return "empty"
        assert target.uncommitted is not None
        uncommitted_lines = target.uncommitted.added + target.uncommitted.removed
        return "tiny" if uncommitted_lines < TINY_MISSING_LINE_LIMIT else "unmerged"

    ratio = target.landed_ratio or 0.0
    if ratio >= SUPERSEDED_RATIO:
        if target.lines_missing <= SUPERSEDED_MAX_MISSING_LINES:
            return "superseded"
        return "mostly-landed"
    if ratio >= MOSTLY_LANDED_RATIO:
        return "mostly-landed"
    if target.lines_missing < TINY_MISSING_LINE_LIMIT:
        return "tiny"
    return "unmerged"


def build_targets(
    git: Git, base: str, inventory: dict, tmp_dir: Path
) -> list[ResidualTarget]:
    branches = inventory["branches"]
    orphan_names = {branch["name"] for branch in branches if branch["cls"] == "orphan"}
    exceptional_worktrees = {
        branch["name"]: branch
        for branch in branches
        if branch.get("worktree_state", "none") in {"dirty", "missing", "unknown"}
    }
    targets_needed = orphan_names | exceptional_worktrees.keys()
    by_name = {branch["name"]: branch for branch in branches}
    jobs = [by_name[name] for name in targets_needed]

    cache = BaseContentCache(git, base)
    with ThreadPoolExecutor(WORKERS) as pool:
        results = list(
            pool.map(
                lambda branch: measure_branch(git, base, cache, branch, tmp_dir),
                jobs,
            )
        )

    results_by_name = {target.name: target for target in results}
    for name, branch in exceptional_worktrees.items():
        target = results_by_name[name]
        if branch.get("worktree_state") == "dirty":
            target.uncommitted = measure_dirty_worktree(git, branch)

    for target in results_by_name.values():
        target.hint = classify_branch_hint(target)

    return sorted(
        results_by_name.values(), key=lambda target: (target.hint, target.name)
    )


def summarize(targets: list[ResidualTarget]) -> dict:
    dirty_targets = [target for target in targets if target.worktree_state == "dirty"]
    return {
        "hints": dict(Counter(target.hint for target in targets)),
        "dirty_worktrees": len(dirty_targets),
        "dirty_worktrees_only_noise": sum(
            target.uncommitted is not None and target.uncommitted.hint == "noise-only"
            for target in dirty_targets
        ),
        "unresolved_worktree_state": sum(
            target.worktree_state in {"missing", "unknown"} for target in targets
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("inventory", help="Path to inventory.py's JSON output")
    parser.add_argument("--out", default="-")
    args = parser.parse_args()

    inventory = json.loads(Path(args.inventory).read_text(encoding="utf-8"))
    git = Git(Path(inventory["repo"]))
    base = inventory["base_sha"]
    tmp_dir = (
        Path(args.out).resolve().parent
        if args.out != "-"
        else Path(tempfile.gettempdir())
    )

    targets = build_targets(git, base, inventory, tmp_dir)
    summary = summarize(targets)

    report = {
        "base_sha": base,
        "summary": summary,
        "targets": [asdict(target) for target in targets],
    }
    text = json.dumps(report, indent=2)

    if args.out == "-":
        print(text)
    else:
        Path(args.out).write_text(text + "\n", encoding="utf-8")

    print(json.dumps(summary, indent=2), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
