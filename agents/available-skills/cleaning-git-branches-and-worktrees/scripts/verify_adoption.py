#!/usr/bin/env python3
"""Read-only check that an adopted Grok clone is a faithful linked worktree.

For each retained original .git (under ~/.grok/worktree-gits/<slug>/<name>) this checks:
  - the clone now carries a worktree pointer at the admin dir the source repo registered;
  - HEAD resolves to the same commit as the retained metadata;
  - the staged entries (index) match the retained metadata;
  - every branch the clone had, and its stash tip, exist in the source repo.

Only refs/heads and refs/stash are read: Grok also keeps binary artifacts under other
refs/ subtrees (refs/codex/turn-diffs), which are not refs and must not be read as text.

One JSON line per clone on stdout, flushed. --limit N and --slug restrict the run;
--only-failing FILE re-checks just the backups a previous run reported as failed.
"""

import argparse
import json
import os
import re
import subprocess
from pathlib import Path

ROOT = Path.home() / ".grok/worktree-gits"
GIT = "/usr/bin/git"


def run(args, **kw):
    p = subprocess.run(
        [GIT, *map(str, args)], capture_output=True, env=os.environ, check=False, **kw
    )
    return p.returncode, p.stdout.decode(errors="replace")


def batch_check(src, shas):
    """Commit SHAs present in `src`'s object store; raise if git itself fails."""
    if not shas:
        return set()
    p = subprocess.run(
        [GIT, "-C", str(src), "cat-file", "--batch-check"],
        input="".join(s + "\n" for s in shas).encode(),
        capture_output=True,
        env=os.environ,
        check=False,
    )
    if p.returncode:
        raise RuntimeError(
            f"cat-file --batch-check failed: {p.stderr.decode(errors='replace')[:200]}"
        )
    return {
        f[0]
        for f in (line.split() for line in p.stdout.decode().splitlines())
        if f[1:2] == ["commit"]
    }


def packed(gitdir):
    path = Path(gitdir) / "packed-refs"
    if not path.exists():
        return {}
    out = {}
    for line in path.read_text(errors="replace").splitlines():
        if line and line[0] not in "#^ ":
            sha, name = line.split(" ", 1)
            out[name] = sha
    return out


def heads(gitdir):
    found = {}
    base = Path(gitdir) / "refs/heads"
    if base.exists():
        for f in base.rglob("*"):
            # Dropbox syncs Finder metadata (.DS_Store) into refs/heads; only real refs count.
            if f.is_file() and not any(
                part.startswith(".") for part in f.relative_to(base).parts
            ):
                sha = f.read_text(errors="replace").split()[0]
                if re.fullmatch(r"[0-9a-f]{40,64}", sha):
                    found[f"refs/heads/{f.relative_to(base)}"] = sha
    for name, sha in packed(gitdir).items():
        if name.startswith("refs/heads/"):
            found.setdefault(name, sha)
    return found


def stash(gitdir):
    loose = Path(gitdir) / "refs/stash"
    if loose.is_file():
        sha = loose.read_text(errors="replace").split()[0]
        if re.fullmatch(r"[0-9a-f]{40,64}", sha):
            return sha
    return packed(gitdir).get("refs/stash")


def check(backup, quick):
    row = {"backup": str(backup)}
    try:
        src = Path(
            (backup / "grok-worktree-source").read_text(errors="replace").strip()
        )
        row["source"] = str(src)
        ident = backup.name.removeprefix("subagent-")
        ident = ident[:8] + "-" + ident[-4:]
        _, common = run(
            ["-C", src, "rev-parse", "--path-format=absolute", "--git-common-dir"]
        )
        admin = Path(common.strip()) / "worktrees" / f"grok-link-{ident}"
        current = Path((admin / "gitdir").read_text(errors="replace").strip()).parent
        row["path"] = str(current)
        pointer = (current / ".git").read_text(errors="replace").strip()
        if pointer != f"gitdir: {admin}":
            raise RuntimeError(f"pointer mismatch: {pointer!r}")
        old_head = (backup / "HEAD").read_text(errors="replace").strip()
        new_head = (admin / "HEAD").read_text(errors="replace").strip()
        row["head"] = new_head
        if not quick:
            _, old_idx = run(["--git-dir", backup, "ls-files", "--stage", "-z"])
            _, new_idx = run(["-C", current, "ls-files", "--stage", "-z"])
            if old_idx != new_idx:
                raise RuntimeError("staged entries differ from retained index")
        _, old_commit = run(["--git-dir", backup, "rev-parse", "HEAD"])
        _, new_commit = run(["-C", current, "rev-parse", "HEAD"])
        if old_commit.strip() != new_commit.strip():
            raise RuntimeError(
                f"HEAD commit differs: {old_commit.strip()[:12]} vs {new_commit.strip()[:12]}"
            )
        # The clone's branch is re-pointed at grok/<id>/<name> so it cannot collide with the
        # source repo's own checkout; a clone on a detached HEAD is given grok/<id>/detached.
        if old_head != new_head:
            branch = (
                old_head.removeprefix("ref: refs/heads/")
                if old_head.startswith("ref: ")
                else "detached"
            )
            row["branch_rewritten"] = branch
            if new_head != f"ref: refs/heads/grok/{ident}/{branch}":
                raise RuntimeError(f"HEAD points somewhere unexpected: {new_head!r}")
        wanted = heads(backup)
        tip = stash(backup)
        row["branches"] = len(wanted)
        row["had_stash"] = bool(tip)
        shas = sorted(set(wanted.values()) | ({tip} if tip else set()))
        have = batch_check(src, shas)
        row["missing_objects"] = sorted(set(shas) - have)
        row["ok"] = not row["missing_objects"]
        if not row["ok"]:
            row["error"] = (
                f"{len(row['missing_objects'])} commit(s) absent from source repo"
            )
    except (OSError, RuntimeError, ValueError, KeyError) as e:
        # Any per-clone failure is reported against that clone, never aborts the sweep.
        row["ok"] = False
        row["error"] = str(e)
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--slug")
    ap.add_argument("--quick", action="store_true", help="skip the index comparison")
    ap.add_argument(
        "--only-failing", help="JSONL from a previous run; re-check its failures"
    )
    a = ap.parse_args()
    if a.only_failing:
        want = set()
        for line in Path(a.only_failing).read_text(errors="replace").splitlines():
            line = line.strip()
            if line:
                row = json.loads(line)
                if isinstance(row, dict) and row.get("ok") is False:
                    want.add(row["backup"])
        backups = sorted(Path(p) for p in want)
    else:
        backups = sorted(p for p in ROOT.glob("*/subagent-*") if p.is_dir())
        if a.slug:
            backups = [b for b in backups if b.parent.name == a.slug]
        if a.limit:
            backups = backups[: a.limit]
    bad = 0
    for b in backups:
        row = check(b, a.quick)
        bad += not row["ok"]
        print(json.dumps(row), flush=True)
    print(json.dumps({"summary": {"checked": len(backups), "failed": bad}}), flush=True)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
