"""subagent-model-guard.py: coverage here is payload-only: untyped spawn
injects model=sonnet on Claude Code, an explicit model or a named agent type
passes through, Grok Build skips injection, and non-Agent tools are silent.
"""

from __future__ import annotations

import pytest
from hook_harness import HookRunner

PY_HOOK = "subagent-model-guard.py"
# Empty string overrides a GROK_SESSION_ID inherited from the test runner
# (pytest under Grok Build would otherwise skip every Claude inject case).
CLAUDE_ENV = {"GROK_SESSION_ID": ""}
GROK_ENV = {"GROK_SESSION_ID": "sess-grok"}


def assert_clean_run(run) -> None:
    assert run.exit_code == 0
    assert run.stderr == ""
    assert not run.failed_open, run.log


def _agent(**tool_input) -> dict:
    return {"tool_name": "Agent", "tool_input": tool_input}


PAYLOAD_CASES: dict[str, dict] = {
    "untyped-absent-injects-sonnet": _agent(prompt="x"),
    "untyped-general-purpose-injects-sonnet": _agent(
        subagent_type="general-purpose", prompt="x"
    ),
    "untyped-claude-injects-sonnet": _agent(subagent_type="claude", prompt="x"),
    "explicit-model-passthrough": _agent(
        subagent_type="general-purpose", model="opus", prompt="x"
    ),
    "named-agent-type-passthrough": _agent(subagent_type="reviewer", prompt="x"),
    "grok-camelcase-untyped": {
        "toolName": "spawn_subagent",
        "toolInput": {"subagentType": "general-purpose", "prompt": "x"},
    },
    "unrelated-tool-silent": {"tool_name": "Read", "tool_input": {"file_path": "/x"}},
    "empty-stdin-silent": "",
}


INJECTS_SONNET = frozenset(
    {
        "untyped-absent-injects-sonnet",
        "untyped-general-purpose-injects-sonnet",
        "untyped-claude-injects-sonnet",
    }
)


@pytest.mark.parametrize("name", PAYLOAD_CASES)
def test_port_decides_on_payload(hooks: HookRunner, name: str) -> None:
    env = GROK_ENV if name.startswith("grok-") else CLAUDE_ENV
    run = hooks.session(name, env=env).run_payload(PY_HOOK, PAYLOAD_CASES[name])
    assert_clean_run(run)
    if name in INJECTS_SONNET:
        assert run.output["hookSpecificOutput"]["updatedInput"]["model"] == "sonnet"
    elif name.endswith("-silent") or name.startswith("grok-"):
        assert run.stdout == ""
    else:
        assert run.stdout == ""  # passthrough: silent no-objection


def test_grok_session_env_skips_inject_on_agent_payload(hooks: HookRunner) -> None:
    """Grok compat remaps spawn_subagent to Task; GROK_SESSION_ID is the harness signal."""
    run = hooks.session("grok-env", env=GROK_ENV).run_payload(
        PY_HOOK, _agent(prompt="x")
    )
    assert_clean_run(run)
    assert run.stdout == ""
    assert "Grok Build rejects explicit model" in run.log


def test_spawn_subagent_skips_inject_without_session_env(hooks: HookRunner) -> None:
    """Native Grok tool name is enough even when GROK_SESSION_ID is unset."""
    run = hooks.session("grok-tool", env=CLAUDE_ENV).run_payload(
        PY_HOOK, PAYLOAD_CASES["grok-camelcase-untyped"]
    )
    assert_clean_run(run)
    assert run.stdout == ""
    assert "Grok Build rejects explicit model" in run.log
