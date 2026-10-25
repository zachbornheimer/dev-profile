"""run_command is the only shell runner, so Bash-keyed guards must see it too.

The instructions require every command to go through run_command, which reaches
the hooks as an MCP tool name. Without an alias, every shell guard goes silent
for exactly the tool the rules force the model to use.
"""

from __future__ import annotations

import pytest
from hook_harness import HookRunner

SEARCH_SCOPE_GUARD = "search-scope-guard.py"
REPO_CWD = "/Users/zbornheimer/Developer/Personal/zq"

# The prefixed name Claude Code sends, and the bare capability name other
# harnesses send.
RUN_COMMAND_TOOL_NAMES = (
    "mcp__capability__agentmux_capability_run_command",
    "agentmux_capability_run_command",
)


def run_command_payload(tool_name: str, command: str) -> dict:
    return {
        "hook_event_name": "PreToolUse",
        "tool_name": tool_name,
        "tool_input": {"command": command, "cwd": REPO_CWD},
        "cwd": REPO_CWD,
    }


@pytest.mark.parametrize("tool_name", RUN_COMMAND_TOOL_NAMES)
def test_search_scope_guard_denies_find_through_run_command(
    hooks: HookRunner, tool_name: str
) -> None:
    run = hooks.run_payload(
        SEARCH_SCOPE_GUARD, run_command_payload(tool_name, "find ~ -name x")
    )
    assert not run.failed_open
    assert run.decision == "deny", run.stdout


@pytest.mark.parametrize("tool_name", RUN_COMMAND_TOOL_NAMES)
def test_search_scope_guard_stays_silent_for_scoped_run_command(
    hooks: HookRunner, tool_name: str
) -> None:
    run = hooks.run_payload(
        SEARCH_SCOPE_GUARD, run_command_payload(tool_name, "timeout 60 fd -e py .")
    )
    assert not run.failed_open
    assert run.decision == "none", run.stdout
