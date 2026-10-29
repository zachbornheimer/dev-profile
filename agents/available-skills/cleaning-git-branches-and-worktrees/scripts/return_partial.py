#!/usr/bin/env python3
"""Return the worktrees a stopped relocation pass had already moved.

The Dropbox-source pass was stopped after moving seven eapp-system worktrees into
~/Developer/Software-Automation-Holdings/.worktrees. Those belong to a duplicate
checkout under ~/Dropbox, so they go back beside the rest of that slug's clones.

Dry run by default; --apply moves.
"""

import argparse
import subprocess
import sys

GIT = "/usr/bin/git"
GROK = "/Users/zbornheimer/.grok/worktrees"
BACKUPS = "/Users/zbornheimer/.grok/worktree-gits"


def git(repo, *a):
    p = subprocess.run(
        [GIT, "-C", repo, *a], capture_output=True, text=True, check=False
    )
    return p.returncode, p.stdout.strip(), p.stderr.strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("repo")
    ap.add_argument("slug")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    rc, out, err = git(a.repo, "worktree", "list", "--porcelain")
    if rc:
        sys.exit(err)
    pairs = []
    for block in out.split("\n\n"):
        path = branch = None
        for line in block.splitlines():
            if line.startswith("worktree "):
                path = line[9:]
            elif line.startswith("branch refs/heads/grok/"):
                branch = line[len("branch refs/heads/") :]
        if path and branch:
            pairs.append((path, branch))
    moved = 0
    for path, branch in pairs:
        ident = branch.split("/")[1]  # <8hex>-<4hex>
        matches = [
            p.name
            for p in __import__("pathlib").Path(BACKUPS, a.slug).glob("subagent-*")
            if f"{p.name[9:17]}-{p.name[-4:]}" == ident
        ]
        if len(matches) != 1:
            print(f"skip {branch}: cannot resolve backup name ({matches})")
            continue
        dest = f"{GROK}/{a.slug}/{matches[0]}"
        if path == dest:
            continue
        print(f"{'move' if a.apply else 'would move'} {path} -> {dest}")
        if a.apply:
            rc, _, err = git(a.repo, "worktree", "move", path, dest)
            if rc:
                print(f"  FAILED: {err}")
                continue
        moved += 1
    print(f"{'moved' if a.apply else 'would move'}: {moved}")


if __name__ == "__main__":
    main()
