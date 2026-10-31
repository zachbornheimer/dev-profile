"""Tests for gemini-filter-resume.py (Stop hook via hook_common / agent-hooks)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from hook_harness import HookRun, HookRunner, HookSession

PY_HOOK = "gemini-filter-resume.py"
STEM = "gemini-filter-resume"
BLOCK = "block"
SILENT = "none"
FILTER_MSG = (
    "This request was blocked by Gemini's filters. They can occasionally trigger "
    "by mistake on safe coding, security, or biology-related queries."
)
OMP_FILTER_MSG = "Request blocked by Google (PROHIBITED_CONTENT)"


@pytest.fixture
def state(hooks: HookRunner) -> HookSession:
    return hooks.session(STEM)


def assert_clean_run(run: HookRun) -> None:
    assert run.exit_code == 0
    assert run.stderr == ""
    assert not run.failed_open, run.log


def _omp_transcript(
    tmp_path: Path, rows: list[dict], name: str = "omp-session.jsonl"
) -> str:
    header = [
        {"type": "title", "v": 1, "title": "", "pad": " " * 80},
        {"type": "session", "version": 3, "id": "s1", "cwd": "/tmp"},
    ]
    path = tmp_path / name
    path.write_text(
        "\n".join(json.dumps(r, separators=(",", ":")) for r in [*header, *rows]) + "\n"
    )
    return str(path)


def test_ladder_please_continue_then_restate_then_allow(
    state: HookSession, tmp_path: Path
) -> None:
    transcript = _omp_transcript(
        tmp_path,
        [
            {
                "type": "message",
                "message": {
                    "role": "user",
                    "attribution": "user",
                    "content": [{"type": "text", "text": "fix the parser edge case"}],
                },
            },
            {
                "type": "message",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": ""}],
                    "stopReason": "error",
                    "errorMessage": FILTER_MSG,
                },
            },
        ],
    )
    payload = {
        "session_id": "s1",
        "hook_event_name": "Stop",
        "transcript_path": transcript,
        "last_assistant_message": "",
    }

    first = state.run_payload(PY_HOOK, payload)
    second = state.run_payload(PY_HOOK, payload)
    third = state.run_payload(PY_HOOK, payload)

    assert_clean_run(first)
    assert_clean_run(second)
    assert_clean_run(third)

    assert first.decision == BLOCK
    assert (first.output or {}).get("reason") == "please continue"

    assert second.decision == BLOCK
    reason_two = (second.output or {}).get("reason", "")
    assert "fix the parser edge case" in reason_two
    assert "blocked by Gemini" not in reason_two

    assert third.decision == SILENT


def test_non_filter_stop_resets_ladder(state: HookSession, tmp_path: Path) -> None:
    blocked_transcript = _omp_transcript(
        tmp_path,
        [
            {
                "type": "message",
                "message": {
                    "role": "user",
                    "attribution": "user",
                    "content": "wire the capability route",
                },
            },
            {
                "type": "message",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": ""}],
                    "stopReason": "error",
                    "errorMessage": OMP_FILTER_MSG,
                },
            },
        ],
        name="blocked.jsonl",
    )
    ok_transcript = _omp_transcript(
        tmp_path,
        [
            {
                "type": "message",
                "message": {
                    "role": "user",
                    "attribution": "user",
                    "content": "wire the capability route",
                },
            },
            {
                "type": "message",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "All tests pass."}],
                    "stopReason": "stop",
                },
            },
        ],
        name="ok.jsonl",
    )

    first = state.run_payload(
        PY_HOOK,
        {
            "session_id": "s2",
            "hook_event_name": "Stop",
            "transcript_path": blocked_transcript,
        },
    )
    normal = state.run_payload(
        PY_HOOK,
        {
            "session_id": "s2",
            "hook_event_name": "Stop",
            "transcript_path": ok_transcript,
            "last_assistant_message": "All tests pass.",
        },
    )
    again = state.run_payload(
        PY_HOOK,
        {
            "session_id": "s2",
            "hook_event_name": "Stop",
            "transcript_path": blocked_transcript,
        },
    )

    assert_clean_run(first)
    assert_clean_run(normal)
    assert_clean_run(again)

    assert first.decision == BLOCK
    assert (first.output or {}).get("reason") == "please continue"
    assert normal.decision == SILENT
    assert again.decision == BLOCK
    assert (again.output or {}).get("reason") == "please continue"


def test_payload_last_assistant_message_triggers_without_transcript(
    state: HookSession,
) -> None:
    payload = {
        "session_id": "s3",
        "hook_event_name": "Stop",
        "last_assistant_message": FILTER_MSG,
    }

    first = state.run_payload(PY_HOOK, payload)
    second = state.run_payload(PY_HOOK, payload)

    assert_clean_run(first)
    assert_clean_run(second)
    assert first.decision == BLOCK
    assert (first.output or {}).get("reason") == "please continue"
    assert second.decision == BLOCK
    assert (
        second.output or {}
    ).get("reason") == "Continue the original coding task in plain language."
