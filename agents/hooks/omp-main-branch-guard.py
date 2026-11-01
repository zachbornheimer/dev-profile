#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""PreToolUse: forbid committing or pushing custom commits to `main` in oh-my-pi.

`main` in ~/Developer/Personal/oh-my-pi (and `fork/main` on zachbornheimer/oh-my-pi)
is a pure upstream mirror of `can1357/oh-my-pi`. Custom changes must live on named
topic branches off `origin/main` and be registered in `dev-profile/config/omp-rebuild.toml`
(which `dev-profile-omp-sync` merges onto `omp-build`).
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
    "Direct commits, merges, or pushes to 'main' in oh-my-pi are forbidden "
    "('main' mirrors upstream can1357/oh-my-pi). "
    "Create a topic branch off origin/main ('wt -C ~/Developer/Personal/oh-my-pi switch --create feat/<slug> --base origin/main'), "
    "commit and push that topic branch to 'fork', and register it in dev-profile/config/omp-rebuild.toml "
    "via 'dev-profile-omp-sync --include feat/<slug> --compile --push'."
)

GIT_PUSH_MAIN_RE = re.compile(
    r"\bgit\b(?:\s+-C\s+\S+)?\s+push\b[^\n;|&]*\b(?:fork|origin)\b[^\n;|&]*(?:\bHEAD:main\b|\bHEAD:refs/heads/main\b|\bmain\b|\bmain:main\b)"
)
GIT_COMMIT_MERGE_RE = re.compile(r"\bgit\b(?:\s+-C\s+\S+|\s+-c\s+\S+)*\s+(?:commit|merge|cherry-pick)\b")
GIT_C_OMP_RE = re.compile(r"\bgit\s+-C\s+([^\s;|&]+)")
CD_OMP_RE = re.compile(r"\bcd\s+([^\s;|&]+)")


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


def targets_oh_my_pi(command: str, cwd: str) -> Path | None:
    for pattern in (GIT_C_OMP_RE, CD_OMP_RE):
        for match in pattern.finditer(command):
            raw = match.group(1).strip("'\"")
            if "oh-my-pi" in raw and ".worktrees" not in raw:
                return Path(raw).expanduser()
    if "oh-my-pi" in cwd and ".worktrees" not in cwd:
        return Path(cwd).expanduser()
    return None


def decide(event: HookEvent) -> Decision | None:
    command = extract_command(event)
    if not command:
        return None

    cwd = event.field("cwd", "cwd")
    omp_repo = targets_oh_my_pi(command, cwd)
    if omp_repo is None:
        return None

    if GIT_PUSH_MAIN_RE.search(command):
        return Decision.deny(STEER_MESSAGE, log_detail="omp-push-main")

    if GIT_COMMIT_MERGE_RE.search(command):
        if re.search(r"\bgit\s+checkout\s+(?:-b|-B)?\s*(?!main\b)\S+", command):
            return None
        branch = current_branch_of(omp_repo)
        if branch in ("main", "master"):
            return Decision.deny(STEER_MESSAGE, log_detail="omp-commit-main")

    return None


if __name__ == "__main__":
    run_hook(HOOK_NAME, decide)
