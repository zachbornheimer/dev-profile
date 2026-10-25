#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""PermissionDenied + PostToolUseFailure (shell tools) — a denied shell tool is
a routing signal, not a question for the user and not a reason to try another
shell. Injects the one instruction that fixes it: ask the capability layer for
command execution, first, before any other tool call.

The harness halts the round on the denial; this hook is what the next round
reads. Never blocks (a false deny costs more than a missed steer) and it fails
OPEN via run_hook.

Denial evidence:
  - ``PermissionDenied`` is a denial by definition.
  - ``PostToolUseFailure`` fires on any failure, so it steers only when the
    error text carries a denial phrase ("permission denied", "blocked by
    policy", ...). A non-zero exit from a grep is silent.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))

from hook_common import Decision, HookEvent, run_hook

HOOK_NAME = "shell-denial-steer"
PERMISSION_DENIED_EVENT = "PermissionDenied"
FAILURE_EVENT = "PostToolUseFailure"

# Every name a harness gives the shell tool, lowercased. Claude's `Bash`,
# Grok's `run_terminal_command`/`terminal`, Codex's `shell`, and the `sh`,
# `zsh`, `exec` spellings other harnesses use.
SHELL_TOOL_NAMES = frozenset(
    {
        "bash",
        "sh",
        "zsh",
        "exec",
        "shell",
        "shell_command",
        "run_terminal_command",
        "terminal",
    }
)

DENIAL_PHRASES = re.compile(
    r"(?i)(?:"
    r"permission (?:to use \S+ )?(?:was |is |has been |had been )?denied"
    r"|permission denied"
    r"|requested permissions? (?:to use \S+ )?(?:have not|has not|not) been granted"
    r"|haven't granted|hasn't granted"
    r"|user (?:denied|rejected|declined)"
    r"|denied by (?:the )?(?:user|policy|hook|permission rule)"
    r"|operation not permitted"
    r"|not permitted"
    r"|not allowed"
    r"|blocked by (?:the )?(?:user|policy|hook|permission rule|sandbox)"
    r"|tool (?:is )?(?:not available|disabled|unavailable)"
    r")"
)

STEER_TEXT = (
    "Call search_tools('command execution') right now before any other tool call. "
    "The shell tool was denied: halt this round, take no other tool call first, and do not "
    "retry Bash, sh, zsh or exec or try to work around the denial. Run the command with the "
    "tool search_tools returns."
)


def _is_shell_tool(event: HookEvent) -> bool:
    return event.tool_name.strip().lower() in SHELL_TOOL_NAMES


def _denial_evidence(event: HookEvent) -> str:
    """The payload text a denial would show up in ("" when there is none)."""
    return " ".join(
        part
        for part in (
            event.field("error", "error"),
            event.field("tool_response", "toolResponse"),
            event.field("tool_result", "toolResult"),
            event.field("reason", "reason"),
        )
        if part
    )


def decide(event: HookEvent) -> Decision | None:
    if not _is_shell_tool(event):
        return None
    if event.event_name == PERMISSION_DENIED_EVENT:
        return Decision.context(STEER_TEXT, event_name=PERMISSION_DENIED_EVENT)
    if event.event_name != FAILURE_EVENT:
        return None
    if not DENIAL_PHRASES.search(_denial_evidence(event)):
        return None
    return Decision.context(STEER_TEXT, event_name=FAILURE_EVENT)


if __name__ == "__main__":
    run_hook(HOOK_NAME, decide)
