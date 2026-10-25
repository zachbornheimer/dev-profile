"""work-order-verify.py: silent/fail-open payload cases.

The success path (scope diff + acceptance run against a real git worktree,
recorded into state/work-orders/<id>.json, then read back by a repeat call)
needs ONE state dir shared across two hook invocations; see
test_work_order_verification_flows.py.
"""

from __future__ import annotations

import json

from hook_harness import HookRunner

PY_HOOK = "work-order-verify.py"


def assert_clean_run(run) -> None:
    assert run.exit_code == 0
    assert run.stderr == ""
    assert not run.failed_open, run.log


def test_no_transcript_path_is_silent(hooks: HookRunner) -> None:
    run = hooks.run_payload(PY_HOOK, {"agent_id": "a1"})
    assert_clean_run(run)
    assert run.stdout == ""


def test_no_marker_in_transcript_is_silent(hooks: HookRunner, tmp_path) -> None:
    transcript = tmp_path / "agent.jsonl"
    transcript.write_text(
        json.dumps(
            {"type": "user", "cwd": str(tmp_path), "message": {"content": "no marker"}}
        )
        + "\n"
    )
    run = hooks.run_payload(
        PY_HOOK, {"agent_transcript_path": str(transcript), "agent_id": "a1"}
    )
    assert_clean_run(run)
    assert run.stdout == ""


def test_empty_stdin_is_silent(hooks: HookRunner) -> None:
    run = hooks.run_payload(PY_HOOK, "")
    assert_clean_run(run)
    assert run.stdout == ""
