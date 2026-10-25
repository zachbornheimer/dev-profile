"""completion-gate.py: payload handling and the go-test FAIL/PASS matcher.

The TypeSafe-judged paths, including what happens when TypeSafe can't answer,
are tested in test_completion_gate_judged.py. Sequential/session-lifetime cases
(reject cap, /goal re-arm, turn budget) live in
test_completion_gate_sequential.py.
"""

from __future__ import annotations

from typing import Any

import pytest
from hook_harness import FIXTURES_DIR, HookRun, HookRunner

PY_HOOK = "completion-gate.py"
STEM = "completion-gate"
BLOCK = "block"
ALLOW = "allow"
FAKE_JUDGE = FIXTURES_DIR / "turn-judge" / "fake_judge.py"
TURN_JUDGE_CLI_ENV = "HC_TURN_JUDGE_CLI"
TURN_JUDGE_FAKE_ENV = "TURN_JUDGE_FAKE"
TYPESAFE_UNAVAILABLE = "unavailable"


def use_fake_judge(
    monkeypatch: pytest.MonkeyPatch, mode: str = TYPESAFE_UNAVAILABLE
) -> None:
    """Point the hook's TypeSafe judge at fake_judge.py in ``mode`` (see its docstring)."""
    monkeypatch.setenv(TURN_JUDGE_CLI_ENV, str(FAKE_JUDGE))
    monkeypatch.setenv(TURN_JUDGE_FAKE_ENV, mode)


@pytest.fixture(autouse=True)
def typesafe_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    use_fake_judge(monkeypatch)


def assert_clean_run(run: HookRun) -> None:
    assert run.exit_code == 0
    assert run.stderr == ""
    assert not run.failed_open, run.log


def decision_shape(run: HookRun) -> str:
    return BLOCK if (run.output or {}).get("decision") == "block" else ALLOW


@pytest.mark.parametrize(
    "name",
    ["grok-camelcase-no-message-silent", "empty-stdin-silent"],
)
def test_port_decides_on_payload(hooks: HookRunner, name: str) -> None:
    payload: dict[str, Any] | str
    if name == "empty-stdin-silent":
        payload = ""
    else:
        payload = {
            "sessionId": "hgtest-cg-grok",
            "hookEventName": "Stop",
            "reason": "end_turn",
        }
    run = hooks.run_payload(PY_HOOK, payload)
    assert_clean_run(run)
    assert run.stdout == ""
