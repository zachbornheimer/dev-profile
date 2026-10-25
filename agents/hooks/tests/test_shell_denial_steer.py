"""shell-denial-steer.py: a denied shell tool injects the routing instruction.

The steer is the exact sentence the operator contract names, and it fires only
on a denial — a failed shell command that was not denied stays silent.
"""

from __future__ import annotations

import pytest
from hook_harness import HookRunner

PY_HOOK = "shell-denial-steer.py"
STEER_SENTENCE = "Call search_tools('command execution') right now before any other tool call."


def _denied(tool_name: str = "Bash") -> dict:
    return {
        "hook_event_name": "PermissionDenied",
        "tool_name": tool_name,
        "tool_input": {"command": "ls"},
    }


def _failed(tool_name: str, error: str) -> dict:
    return {
        "hook_event_name": "PostToolUseFailure",
        "tool_name": tool_name,
        "tool_input": {"command": "ls"},
        "error": error,
    }


PAYLOAD_CASES: dict[str, tuple[dict | str, bool]] = {
    "bash-denied-steers": (_denied("Bash"), True),
    "sh-denied-steers": (_denied("sh"), True),
    "zsh-denied-steers": (_denied("zsh"), True),
    "exec-denied-steers": (_denied("exec"), True),
    "grok-terminal-denied-steers": (
        {
            "hookEventName": "PermissionDenied",
            "toolName": "run_terminal_command",
            "toolInput": {"command": "ls"},
        },
        True,
    ),
    "denial-in-failure-error-steers": (
        _failed("Bash", "Claude requested permissions to use Bash, but you haven't granted it yet."),
        True,
    ),
    "permission-denied-error-steers": (_failed("Bash", "permission denied"), True),
    "permission-to-use-has-been-denied-steers": (
        _failed("Bash", "Permission to use Bash has been denied."),
        True,
    ),
    "zsh-denial-in-failure-steers": (
        _failed("zsh", "The user denied this command: zsh"),
        True,
    ),
    "failed-command-not-denied-silent": (_failed("Bash", "grep: no matches found"), False),
    "non-shell-tool-denied-silent": (_denied("Read"), False),
    "success-event-silent": (
        {"hook_event_name": "PostToolUse", "tool_name": "Bash", "tool_input": {"command": "ls"}},
        False,
    ),
    "empty-stdin-silent": ("", False),
}


@pytest.mark.parametrize("name", PAYLOAD_CASES)
def test_decides(hooks: HookRunner, name: str) -> None:
    payload, steers = PAYLOAD_CASES[name]
    run = hooks.run_payload(PY_HOOK, payload)
    assert run.exit_code == 0
    assert run.stderr == ""
    assert not run.failed_open
    if steers:
        assert run.decision == "context"
        context = (run.output or {})["hookSpecificOutput"]["additionalContext"]
        assert STEER_SENTENCE in context
        assert "halt this round" in context
    else:
        assert run.stdout == ""
