"""completion-gate.py: the session-lifetime sequences from run.sh — reject
cap, /goal re-arm, and turn budget — that reuse one state dir across calls
for the same session id (hook_harness.HookSession).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from hook_harness import HookRun, HookRunner, HookSession
from test_completion_gate import (
    PY_HOOK,
    STEM,
    assert_clean_run,
)
from test_completion_gate_judged import DEFERRED, replay

BLOCK = "block"
SESSION_REJECT_CAP = 5
SESSION_TURN_BUDGET = 80
REJECT_CAP_FIXTURE = "completion-reject-cap-identical-claim.json"
REJECT_CAP_ENV = {"HC_STOP_REJECT_CAP": str(SESSION_REJECT_CAP)}


@pytest.fixture(autouse=True)
def typesafe_blocks(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """TypeSafe judges every stop a deferral, so each call would block before the caps."""
    replay(monkeypatch, tmp_path, DEFERRED)


def is_block(run: HookRun) -> bool:
    return (run.output or {}).get("decision") == BLOCK


@pytest.fixture
def state(hooks: HookRunner) -> HookSession:
    return hooks.session(STEM)


def test_reject_cap_blocks_five_times_then_hands_off(state: HookSession) -> None:
    for attempt in range(1, SESSION_REJECT_CAP + 1):
        run = state.run_fixture(PY_HOOK, REJECT_CAP_FIXTURE, REJECT_CAP_ENV)
        assert_clean_run(run)
        assert is_block(run), f"attempt {attempt} should still block: {run.stdout}"

    sixth = state.run_fixture(PY_HOOK, REJECT_CAP_FIXTURE, REJECT_CAP_ENV)
    assert_clean_run(sixth)
    assert not is_block(sixth), f"6th attempt should stop blocking: {sixth.stdout}"
    assert sixth.output is None
    assert sixth.log.endswith(f"\tallow\treject-cap-reached-{SESSION_REJECT_CAP}\n")


def test_goal_four_denials_still_blocks(state: HookSession) -> None:
    run = state.run_fixture(
        PY_HOOK, "completion-goal-four-denials.json", REJECT_CAP_ENV
    )
    assert_clean_run(run)
    assert is_block(run)


def test_goal_five_denials_stops_rearming_and_writes_handoff(
    state: HookSession,
) -> None:
    run = state.run_fixture(
        PY_HOOK, "completion-goal-five-denials.json", REJECT_CAP_ENV
    )

    assert_clean_run(run)
    assert not is_block(run)
    assert run.output is None
    assert "goal-deny-cap-reached-" in run.log

    handoff = state.state_dir / "goal-handoff-hgtest-g5.md"
    assert handoff.is_file()
    assert "proveably resolved" in handoff.read_text()


def test_goal_exhausted_condition_stays_allowed_after_compaction(
    state: HookSession,
) -> None:
    state.run_fixture(PY_HOOK, "completion-goal-five-denials.json", REJECT_CAP_ENV)

    run = state.run_fixture(
        PY_HOOK, "completion-goal-exhausted-still-allow.json", REJECT_CAP_ENV
    )

    assert_clean_run(run)
    assert not is_block(run)


def test_turn_budget_reached_allows_with_handoff_twice(state: HookSession) -> None:
    fixture = "completion-turn-budget-handoff-allow.json"
    env = {"HC_TURN_BUDGET": str(SESSION_TURN_BUDGET)}

    for _ in range(2):
        run = state.run_fixture(PY_HOOK, fixture, env)
        assert_clean_run(run)
        assert not is_block(run)
        assert run.output is None
        assert f"turn-budget-reached-{SESSION_TURN_BUDGET}" in run.log


def test_turn_budget_not_yet_reached_still_blocks(state: HookSession) -> None:
    run = state.run_fixture(
        PY_HOOK, "completion-turn-budget-handoff-allow.json", {"HC_TURN_BUDGET": "81"}
    )
    assert_clean_run(run)
    assert is_block(run)
