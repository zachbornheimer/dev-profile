#!/usr/bin/env python3
"""Move linked worktrees to the wt worktree-path template destination, without wt's
status scan (which costs minutes per worktree on very large trees).

Same end state `wt step relocate` produces: <repo_path>/../.worktrees/<repo>-<sanitized branch>.
Verify afterwards with `wt -C <repo> step relocate --dry-run`, which must report nothing.

Dry run by default; pass --apply to move.
"""

import argparse
import os
import subprocess
import sys

GIT = "/usr/bin/git"


def git(repo, *a):
    p = subprocess.run(
        [GIT, "-C", repo, *a], capture_output=True, text=True, check=False
    )
    return p.returncode, p.stdout.strip(), p.stderr.strip()


def listed(repo):
    """[(path, branch)] for every linked worktree, from the porcelain listing."""
    rc, out, err = git(repo, "worktree", "list", "--porcelain")
    if rc:
        sys.exit(f"worktree list failed: {err}")
    found = []
    for block in out.split("\n\n"):
        path = branch = None
        for line in block.splitlines():
            if line.startswith("worktree "):
                path = line[9:]
            elif line.startswith("branch refs/heads/"):
                branch = line[len("branch refs/heads/") :]
        if path and branch:
            found.append((path, branch))
    return found


def sanitize(branch):
    return branch.replace("/", "-")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("repo")
    ap.add_argument("--prefix", help="only move branches starting with this")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    repo = a.repo.rstrip("/")
    parent_worktrees = repo.rsplit("/", 1)[0] + "/.worktrees"
    name = repo.rsplit("/", 1)[1]
    moved = skipped = 0
    for path, branch in listed(repo):
        if a.prefix and not branch.startswith(a.prefix):
            continue
        dest = f"{parent_worktrees}/{name}-{sanitize(branch)}"
        if path == dest:
            skipped += 1
            continue
        if path == repo:
            print(f"skip main worktree: {branch}")
            continue
        print(f"{'move' if a.apply else 'would move'} {path} -> {dest}")
        if a.apply:
            rc, _, err = git(repo, "worktree", "move", path, dest)
            if rc and "submodules" in err:
                # git refuses worktree move for a tree containing submodules; a plain
                # directory move followed by `worktree repair` is the supported route.
                if os.path.exists(dest):
                    print(f"  FAILED {branch}: destination exists")
                    continue
                os.rename(path, dest)
                rc, _, err = git(repo, "worktree", "repair", dest)
            if rc:
                print(f"  FAILED {branch}: {err}")
                continue
        moved += 1
    print(
        f"{'moved' if a.apply else 'would move'}: {moved}, already in place: {skipped}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
