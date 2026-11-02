#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""PreToolUse: forbid committing, merging (including `wt merge` / `wt land`), or pushing custom commits to `main` in oh-my-pi.

`main` in ~/Developer/Personal/oh-my-pi (and `fork/main` on zachbornheimer/oh-my-pi)
is a read-only upstream mirror of `can1357/oh-my-pi`. Custom changes live on named
topic branches off `origin/main`, pushed to the fork and listed in the fork's
`.github/omp-rebuild.toml` (on the `ci` branch), which CI builds into a release
that `mise up` installs.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))

from hook_common import Decision, HookEvent, run_hook

HOOK_NAME = "omp-main-branch-guard"

STEER_MESSAGE = (
    "Direct commits, merges (including 'wt merge' / 'wt land'), or pushes to 'main' in oh-my-pi are forbidden "
    "('main' is a read-only mirror of upstream can1357/oh-my-pi). "
    "Create a topic branch off origin/main ('wt -C ~/Developer/Personal/oh-my-pi switch --create feat/<slug> --base origin/main'), "
    "commit and push that topic branch to 'fork' ('git push -u fork feat/<slug>'), then add it to the fork's "
    ".github/omp-rebuild.toml on the 'ci' branch so CI builds the next release; 'mise up' installs it."
)

GIT_PUSH_MAIN_RE = re.compile(
    r"\bgit\b(?:\s+-C\s+\S+)?\s+push\b[^\n;|&]*\b(?:fork|origin)\b[^\n;|&]*(?:\bHEAD:main\b|\bHEAD:refs/heads/main\b|\bmain\b|\bmain:main\b)"
)
# `(?![\w-])`: read-only plumbing such as `merge-base` / `merge-tree` is not a merge.
GIT_COMMIT_MERGE_RE = re.compile(
    r"\bgit\b(?:\s+-C\s+\S+|\s+-c\s+\S+)*\s+(?:commit|merge|cherry-pick)(?![\w-])"
)
WT_MERGE_LAND_RE = re.compile(r"\bwt\b(?:\s+-C\s+\S+)?\s+(?:merge|land)\b([^\n;|&]*)")
GIT_C_RE = re.compile(r"\b(?:git|wt)\s+-C\s+([^\s;|&]+)")
CD_ONLY_RE = re.compile(r"^\s*cd\s+([^\s;|&]+)\s*$")


def extract_command(event: HookEvent) -> str:
    cmd = event.tool_input("command")
    if cmd.strip():
        return cmd
    path = event.tool_input("path")
    content = event.tool_input("content")
    if "run_command" in path and content:
        try:
            parsed = json.loads(content)
            if isinstance(parsed, dict) and isinstance(parsed.get("command"), str):
                return parsed["command"]
        except ValueError:
            pass
    return ""


def current_branch_of(repo_path: Path) -> str:
    try:
        res = subprocess.run(
            ["git", "-C", str(repo_path), "symbolic-ref", "--short", "-q", "HEAD"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        return res.stdout.strip()
    except OSError:
        return ""


def classify_target(target_path: str) -> tuple[Path | None, bool]:
    cleaned = target_path.strip("'\"")
    if "oh-my-pi" in cleaned:
        return Path(cleaned).expanduser(), (".worktrees" in cleaned)
    return None, False


def decide(event: HookEvent) -> Decision | None:
    command = extract_command(event)
    if not command:
        return None

    active_cwd = event.field("cwd", "cwd")
    clauses = re.split(r"&&|\|\||;|\n", command)

    for raw_clause in clauses:
        clause = raw_clause.strip()
        if not clause:
            continue
        cd_match = CD_ONLY_RE.match(clause)
        if cd_match:
            active_cwd = cd_match.group(1).strip("'\"")
            continue

        c_match = GIT_C_RE.search(clause)
        clause_target = c_match.group(1) if c_match else active_cwd
        omp_repo, is_worktree = classify_target(clause_target)
        if omp_repo is None:
            continue

        if GIT_PUSH_MAIN_RE.search(clause):
            return Decision.deny(STEER_MESSAGE, log_detail="omp-push-main")

        wt_match = WT_MERGE_LAND_RE.search(clause)
        if wt_match:
            tail = wt_match.group(1) or ""
            if "omp-build" not in tail:
                return Decision.deny(STEER_MESSAGE, log_detail="omp-wt-merge-main")

        if not is_worktree and GIT_COMMIT_MERGE_RE.search(clause):
            branch = current_branch_of(omp_repo)
            if branch in ("main", "master"):
                return Decision.deny(STEER_MESSAGE, log_detail="omp-commit-main")

    return None


if __name__ == "__main__":
    run_hook(HOOK_NAME, decide)
