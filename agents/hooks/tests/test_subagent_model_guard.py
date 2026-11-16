"""subagent-model-guard.py: coverage here is payload-only: untyped spawn
injects model=sonnet, an explicit model or a named agent type passes through,
and non-Agent tools are silent.
"""

from __future__ import annotations

import pytest
from hook_harness import HookRunner

PY_HOOK = "subagent-model-guard.py"


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
    run = hooks.session(name).run_payload(PY_HOOK, PAYLOAD_CASES[name])
    assert_clean_run(run)
    if name in INJECTS_SONNET:
        assert run.output["hookSpecificOutput"]["updatedInput"]["model"] == "sonnet"
    else:
        assert run.stdout == ""  # passthrough or unrelated: silent no-objection
