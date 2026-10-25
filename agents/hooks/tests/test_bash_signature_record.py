"""bash-signature-record.py: no run.sh direct cases exist for this hook (it
only feeds bash-history-*.tsv that two-strikes-gate.py/completion-gate.py
consume, which are tested elsewhere) — so cases are built inline here,
mirroring the shape those existing consumers exercise.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from hook_harness import HookRunner

PY_HOOK = "bash-signature-record.py"


def _bash(session_id: str, event: str, command: str) -> dict:
    return {
        "session_id": session_id,
        "hook_event_name": event,
        "tool_name": "Bash",
        "tool_input": {"command": command},
    }


PAYLOAD_CASES: dict[str, dict | str] = {
    "success-records-signature": _bash(
        "hgtest-bsr1", "PostToolUse", "go test ./models/..."
    ),
    "failure-records-signature": _bash(
        "hgtest-bsr2", "PostToolUseFailure", "go test ./models/..."
    ),
    "skips-leading-var-assignments": _bash(
        "hgtest-bsr3", "PostToolUse", "FOO=bar BAZ=qux go test ./models/..."
    ),
    # hc_command_signature skips an assignment anywhere in the first words, not only leading ones.
    "skips-mid-command-assignments": _bash(
        "hgtest-bsr7", "PostToolUse", "go GOFLAGS=-count=1 test ./models/..."
    ),
    "unrelated-event-silent": _bash(
        "hgtest-bsr4", "PreToolUse", "go test ./models/..."
    ),
    "no-session-id-silent": {
        "hook_event_name": "PostToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "go test ./models/..."},
    },
    "no-command-silent": {
        "session_id": "hgtest-bsr5",
        "hook_event_name": "PostToolUse",
        "tool_name": "Bash",
    },
    "grok-camelcase": {
        "sessionId": "hgtest-bsr6",
        "hookEventName": "post_tool_use",
        "toolName": "run_terminal_command",
        "toolInput": {"command": "ls -la"},
    },
    "malformed-json-silent": "{not valid json",
    "empty-stdin-silent": "",
}


def _history_file(hooks: HookRunner, hook: str, session_id: str) -> list[Path]:
    return list(hooks.state_root.glob(f"{hook}-*/bash-history-{session_id}.tsv"))


def assert_clean_run(run) -> None:
    assert run.exit_code == 0
    assert run.stderr == ""


@pytest.mark.parametrize("name", PAYLOAD_CASES)
def test_port_runs_clean(hooks: HookRunner, name: str) -> None:
    run = hooks.run_payload(PY_HOOK, PAYLOAD_CASES[name])
    assert_clean_run(run)
    assert run.stdout == ""


def test_port_records_success_history_line(hooks: HookRunner) -> None:
    hooks.run_payload(PY_HOOK, PAYLOAD_CASES["success-records-signature"])
    matches = _history_file(hooks, PY_HOOK, "hgtest-bsr1")
    assert matches, "no bash-history file written"
    assert matches[0].read_text().strip().endswith("go test ./models/...\tsuccess")


def test_port_records_failure_history_line(hooks: HookRunner) -> None:
    hooks.run_payload(PY_HOOK, PAYLOAD_CASES["failure-records-signature"])
    matches = _history_file(hooks, PY_HOOK, "hgtest-bsr2")
    assert matches and matches[0].read_text().strip().endswith(
        "go test ./models/...\tfail"
    )


def test_port_skips_leading_var_assignments(hooks: HookRunner) -> None:
    hooks.run_payload(PY_HOOK, PAYLOAD_CASES["skips-leading-var-assignments"])
    matches = _history_file(hooks, PY_HOOK, "hgtest-bsr3")
    assert matches
    line = matches[0].read_text().strip()
    assert "\tgo test ./models/...\tsuccess" in line
    assert "FOO=bar" not in line


def test_port_skips_mid_command_assignments(hooks: HookRunner) -> None:
    hooks.run_payload(PY_HOOK, PAYLOAD_CASES["skips-mid-command-assignments"])
    matches = _history_file(hooks, PY_HOOK, "hgtest-bsr7")
    assert matches
    line = matches[0].read_text().strip()
    assert "\tgo test ./models/...\tsuccess" in line
    assert "GOFLAGS" not in line
