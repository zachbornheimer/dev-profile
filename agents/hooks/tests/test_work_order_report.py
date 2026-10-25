"""work-order-report.py: silent/fail-open payload cases.

The success + idempotent-repeat path (a completed Agent spawn whose
recorded verification gets relayed once, then suppressed on a repeat call)
needs the SAME state dir and transcript layout shared across two hook
invocations; see test_work_order_verification_flows.py.
"""

from __future__ import annotations

import pytest
from hook_harness import HookRunner

PY_HOOK = "work-order-report.py"


def assert_clean_run(run) -> None:
    assert run.exit_code == 0
    assert run.stderr == ""
    assert not run.failed_open, run.log


PAYLOAD_CASES: dict[str, dict | str] = {
    "non-agent-tool-silent": {"tool_name": "Read", "tool_input": {}},
    "not-completed-silent": {
        "tool_name": "Agent",
        "tool_response": {"status": "running", "agentId": "a1"},
    },
    "no-agent-id-silent": {
        "tool_name": "Agent",
        "tool_response": {"status": "completed"},
    },
    "no-transcript-path-silent": {
        "tool_name": "Agent",
        "tool_response": {"status": "completed", "agentId": "a1"},
    },
    "non-jsonl-transcript-silent": {
        "tool_name": "Agent",
        "transcript_path": "/tmp/does-not-matter.txt",
        "tool_response": {"status": "completed", "agentId": "a1"},
    },
    "unreconstructable-transcript-silent": {
        "tool_name": "Agent",
        "transcript_path": "/tmp/definitely-missing-parent-dir-xyz/session.jsonl",
        "tool_response": {"status": "completed", "agentId": "a1"},
    },
    "empty-stdin-silent": "",
}


@pytest.mark.parametrize("name", PAYLOAD_CASES)
def test_port_runs_clean_and_silent(hooks: HookRunner, name: str) -> None:
    run = hooks.run_payload(PY_HOOK, PAYLOAD_CASES[name])
    assert_clean_run(run)
    assert run.stdout == ""
