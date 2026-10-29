#!/usr/bin/env python3
"""Fast invariant check over every adopted Grok clone.

For each retained original .git under ~/.grok/worktree-gits/<slug>/<name>:
  - the worktree the source repo registered for it still points back at that registration;
  - its checkout exists;
  - it lives under ~/Developer/<Org>/.worktrees, unless its source repo is outside
    ~/Developer (the known Dropbox duplicates), which must stay in ~/.grok/worktrees.

No per-worktree git commands, so it finishes in seconds. Exits 1 on any violation.
Use verify_adoption.py for the deep per-clone comparison.
"""

import collections
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path.home() / ".grok/worktree-gits"
GIT = "/usr/bin/git"


def common_dir(src):
    p = subprocess.run(
        [GIT, "-C", src, "rev-parse", "--path-format=absolute", "--git-common-dir"],
        capture_output=True,
        text=True,
        check=False,
    )
    return p.stdout.strip() if p.returncode == 0 else None


def main():
    commons, rows, bad, pruned = {}, [], [], []
    for backup in sorted(p for p in ROOT.glob("*/subagent-*") if p.is_dir()):
        name = backup.name
        ident = name.removeprefix("subagent-")
        ident = ident[:8] + "-" + ident[-4:]
        try:
            src = (backup / "grok-worktree-source").read_text(errors="replace").strip()
            if src not in commons:
                commons[src] = common_dir(src)
            common = commons[src]
            admin = Path(common) / "worktrees" / f"grok-link-{ident}"
            if not (admin / "gitdir").exists():
                # `wt step prune` (a scheduled weekly job on this machine) removes a
                # worktree and its registration once its branch is merged into the default
                # branch and the checkout is clean. That is settled state, not damage.
                pruned.append(
                    {"backup": str(backup), "source": src, "registration": str(admin)}
                )
                continue
            current = Path(
                (admin / "gitdir").read_text(errors="replace").strip()
            ).parent
            pointer = (current / ".git").read_text(errors="replace").strip()
            problems = []
            if pointer != f"gitdir: {admin}":
                problems.append("pointer does not name its registration")
            if not current.is_dir():
                problems.append("checkout missing")
            under_developer = str(current).startswith(
                str(Path.home() / "Developer") + "/"
            )
            source_outside_developer = not str(Path(src)).startswith(
                str(Path.home() / "Developer") + "/"
            )
            if under_developer == source_outside_developer:
                problems.append(f"wrong home: source {src}, checkout {current}")
            row = {"backup": str(backup), "source": src, "path": str(current)}
            if problems:
                row["problems"] = problems
                bad.append(row)
            rows.append(row)
        except (OSError, TypeError) as e:
            # A clone whose registration cannot be read is reported, not fatal.
            bad.append({"backup": str(backup), "error": str(e)})
    where = collections.Counter(
        (
            "Developer"
            if r.get("path", "").startswith(str(Path.home() / "Developer") + "/")
            else "elsewhere"
        )
        for r in rows
    )
    print(
        json.dumps(
            {
                "checked": len(rows),
                "locations": dict(where),
                "pruned": len(pruned),
                "violations": len(bad),
                "details": bad[:20],
            },
            indent=2,
        )
    )
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
