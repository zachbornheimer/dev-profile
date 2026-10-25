#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""PreToolUse (Bash) — branch and worktree lifecycle goes through Worktrunk.

Denies raw git that Worktrunk (`wt`) owns — staging, committing, creating,
switching, merging, rebasing and removing branches/worktrees, plus `gh pr checkout` — and names
the `wt` command to run instead. Rules live in lib/worktree_lifecycle_rules.py.

Registered for Claude Code, Codex, Grok and OpenCode. Fails OPEN on parse
errors or unexpected input, like every guard here.
"""

from __future__ import annotations

import shlex
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))

from command_words import simple_commands
from hook_common import Decision, HookEvent, run_hook
from worktree_lifecycle_rules import lifecycle_violation

HOOK_NAME = "worktree-lifecycle-guard"
REASON = (
    "`{command}` bypasses Worktrunk, which owns the branch/worktree lifecycle. {fix}"
)


def check_bash_command(command: str, cwd: str | None = None) -> Decision | None:
    for argv in simple_commands(command):
        fix = lifecycle_violation(argv, cwd)
        if fix:
            shown = " ".join(argv)
            return Decision.deny(
                REASON.format(command=shown, fix=fix), log_detail=shown
            )
    return None


def bash_command(event: HookEvent) -> str:
    """The command as one shell string, whether sent as text or as an argv array."""
    raw = event.tool_input_section().get("command")
    if isinstance(raw, list) and all(isinstance(word, str) for word in raw):
        return shlex.join(raw)
    return event.tool_input("command")


def decide(event: HookEvent) -> Decision | None:
    if event.tool_name != "Bash":
        return None
    command = bash_command(event)
    if not command:
        return None
    return check_bash_command(command, event.field("cwd", "cwd") or None) or Decision.no_objection(
        "Bash:no-raw-lifecycle-git"
    )


if __name__ == "__main__":
    run_hook(HOOK_NAME, decide)
