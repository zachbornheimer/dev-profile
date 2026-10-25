"""bash-tool-steer.py: every Bash tool call is denied with the one instruction
that routes it to run_command, and every other tool is left alone.

The config registers this hook with on_failure = "block", so the deny is a
block at the harness; the hook itself still exits 0 and stays silent for
anything that is not Bash.
"""

from __future__ import annotations

import pytest
from hook_harness import HookRunner

HOOK = "bash-tool-steer.py"
RUN_COMMAND = "mcp__capability__agentmux_capability_run_command"
SEARCH_TOOLS = 'search_tools("command execution")'


def _bash(command: str = "ls") -> dict:
    return {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": command}}


OTHER_TOOLS = (
    "run_command",
    "mcp__capability__agentmux_capability_run_command",
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
        {"hookEventName": "tool.before", "toolName": "Bash", "toolInput": {"command": "pwd"}},
        True,
    ),
    "empty-stdin-silent": ("", False),
}
PAYLOAD_CASES.update(
    {f"{tool}-silent": ({"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": {}}, False) for tool in OTHER_TOOLS}
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
        assert RUN_COMMAND in reason
        assert "Bash is disabled; use run_command." in reason
        assert SEARCH_TOOLS in reason
    else:
        assert run.stdout == ""
