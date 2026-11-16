"""bash-tool-steer.py: every foreign shell tool call (capital `Bash`, `sh`, `zsh`, ...) is
denied with the one instruction that routes it to omp's native `bash`; lowercase `bash`
and every other tool are left alone.

The config registers this hook with on_failure = "block", so the deny is a
block at the harness; the hook itself still exits 0 and stays silent for
anything that is not a foreign shell.
"""

from __future__ import annotations

import pytest
from hook_harness import HookRunner

HOOK = "bash-tool-steer.py"
SEARCH_TOOLS = 'tool_search { query: "run a shell command" }'


def _bash(command: str = "ls") -> dict:
    return {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": command},
    }


OTHER_TOOLS = (
    "bash",
    "Read",
    "Edit",
    "Write",
    "Grep",
    "Agent",
)

PAYLOAD_CASES: dict[str, tuple[dict | str, bool]] = {
    "bash-ls-denied": (_bash("ls"), True),
    "bash-empty-command-denied": (_bash(""), True),
    "bash-camel-payload-denied": (
        {
            "hookEventName": "tool.before",
            "toolName": "Bash",
            "toolInput": {"command": "pwd"},
        },
        True,
    ),
    "empty-stdin-silent": ("", False),
}
PAYLOAD_CASES.update(
    {
        f"{tool}-silent": (
            {"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": {}},
            False,
        )
        for tool in OTHER_TOOLS
    }
)


@pytest.mark.parametrize("name", PAYLOAD_CASES)
def test_decides(hooks: HookRunner, name: str) -> None:
    payload, denies = PAYLOAD_CASES[name]
    run = hooks.run_payload(HOOK, payload)
    assert run.exit_code == 0
    assert run.stderr == ""
    assert not run.failed_open
    if denies:
        assert run.decision == "deny"
        reason = (run.output or {})["hookSpecificOutput"]["permissionDecisionReason"]
        assert "use omp's native `bash` tool" in reason
        assert "retired" in reason
        assert SEARCH_TOOLS in reason
    else:
        assert run.stdout == ""
