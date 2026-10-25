"""completion-gate.py paths judged by TypeSafe, beyond the shared checks.

1. Go-test result lines count only from real test-command results in a JSONL
   transcript, never from a Read or printed source (the TestFoo false positive).
2. TypeSafe judges the message. fake_judge.py replays TypeSafe answers
   recorded live on the eval set through the real judge-turn CLI, so the
   real policy decides; no network.
3. When TypeSafe is unavailable, crashes, hangs, or prints garbage, the
   gate allows the stop, and the judgment log says why.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from hook_harness import FIXTURES_DIR, HookRun, HookRunner, HookSession
from test_completion_gate import (
    ALLOW,
    BLOCK,
    PY_HOOK,
    STEM,
    TYPESAFE_UNAVAILABLE,
    assert_clean_run,
    decision_shape,
    use_fake_judge,
)

RECORDED_ANSWERS = FIXTURES_DIR / "turn-judge" / "recorded-answers.json"
JUDGMENTS_LOG = "completion-gate-judgments.jsonl"
TIMEOUT_ENV = {"HC_TURN_JUDGE_TIMEOUT_SECS": "1"}
# Eval-set ids whose recorded answers stand in for each kind of turn.
DEFERRED = "F293"  # 'Next action (~1 min): reply "fix split now" or "after the swap."'
LEGIT_WAIT = "F221"  # asks whether a worktree is the user's; nothing else can proceed
FINISHED = "F226"  # plain status report
UNPROVEN = "B248"  # "Hooks branch done ... leak is closed" with no evidence this turn
# Real Stop payloads (transcript + final message) that live TypeSafe let through.
REAL_MISS_FIXTURES = {
    "M-homelab": "completion-gate-real-miss-homelab-blocks.json",
    "M-analytics": "completion-gate-real-miss-analytics-blocks.json",
}
# 'It's a ~10-minute add.' -- never frames the stop as a handoff, so only the
# leaves-doable-work branch (added 2026-09-24) catches it.
THIS_TURN_MISS_ID = "THIS-TURN"
THIS_TURN_MISS_FIXTURE = "completion-gate-real-miss-this-turn-blocks.json"
H5_QUESTION_FIXTURE = "completion-h5-trailing-question-block.json"
H5_BENIGN_FIXTURE = "completion-h5-benign-closer-allow.json"


@pytest.fixture
def state(hooks: HookRunner) -> HookSession:
    return hooks.session(STEM)


def judgments(state: HookSession) -> list[dict]:
    path = state.state_dir / JUDGMENTS_LOG
    return (
        [json.loads(line) for line in path.read_text().splitlines()]
        if path.exists()
        else []
    )


def assert_keep_going_reason(reason: str) -> None:
    """A deferral block tells the agent to act now, never to rephrase the ask."""
    assert reason.startswith("You stopped to wait for the user"), reason
    assert "Do it now" in reason, reason
    assert "same turn" in reason, reason


NEUTRAL_NOUL = {"noul": 0.0, "type": "noul"}
# Questions added to the judge after the answers were recorded; neutral so the
# recorded turn's other answers still decide.
QUESTIONS_ADDED_SINCE_RECORDING = (
    "user_withheld_action",
    "closing_asks_user_preference",
)


def replay(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, eval_id: str) -> None:
    """TypeSafe answers as recorded live for eval item ``eval_id``."""
    answers = tmp_path / f"answers-{eval_id}.json"
    neutral = dict.fromkeys(QUESTIONS_ADDED_SINCE_RECORDING, NEUTRAL_NOUL)
    recorded = json.loads(RECORDED_ANSWERS.read_text())[eval_id]
    answers.write_text(json.dumps(neutral | recorded))
    use_fake_judge(monkeypatch, str(answers))


# --- 2. TypeSafe decides -----------------------------------------------------------


def test_deferred_turn_blocks_and_quotes_the_handoff(
    state: HookSession, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    replay(monkeypatch, tmp_path, DEFERRED)

    run = state.run_fixture(PY_HOOK, H5_BENIGN_FIXTURE)

    assert_clean_run(run)
    assert decision_shape(run) == BLOCK, run.stdout
    assert_keep_going_reason(run.output["reason"])
    [entry] = judgments(state)
    assert (entry["path"], entry["block_kind"], entry["decision"]) == (
        "typesafe",
        "deferred",
        "block",
    )
    assert entry["answers"]["turn_outcome"]["probabilities"]


@pytest.mark.parametrize(("eval_id", "fixture"), sorted(REAL_MISS_FIXTURES.items()))
def test_real_miss_blocks_through_the_hook(
    state: HookSession,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    eval_id: str,
    fixture: str,
) -> None:
    replay(monkeypatch, tmp_path, eval_id)

    run = state.run_fixture(PY_HOOK, fixture)

    assert_clean_run(run)
    assert decision_shape(run) == BLOCK, run.stdout
    assert_keep_going_reason(run.output["reason"])
    [entry] = judgments(state)
    assert (entry["path"], entry["block_kind"]) == ("typesafe", "deferred")


def test_leftover_work_without_a_handoff_blocks_through_the_hook(
    state: HookSession, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Red before the leaves-doable-work branch existed: the old policy allowed this turn."""
    replay(monkeypatch, tmp_path, THIS_TURN_MISS_ID)

    run = state.run_fixture(PY_HOOK, THIS_TURN_MISS_FIXTURE)

    assert_clean_run(run)
    assert decision_shape(run) == BLOCK, run.stdout
    assert "You mentioned work you can still do now" in run.output["reason"]
    [entry] = judgments(state)
    assert (entry["path"], entry["block_kind"]) == ("typesafe", "deferred")
    assert entry["state"]["final_message"]
    assert entry["state"]["user_request"]


@pytest.mark.parametrize("eval_id", [LEGIT_WAIT, FINISHED])
def test_waiting_or_finished_turn_allows(
    state: HookSession, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, eval_id: str
) -> None:
    replay(monkeypatch, tmp_path, eval_id)

    run = state.run_fixture(PY_HOOK, H5_QUESTION_FIXTURE)

    assert_clean_run(run)
    assert decision_shape(run) == ALLOW, run.stdout
    assert run.log.endswith("\tallow\ttypesafe-allow\n")
    assert judgments(state)[0]["path"] == "typesafe"


def test_current_pause_overrides_older_goal(
    state: HookSession, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A pause or information-only request still in force stops the turn.

    The older goal stays unfinished and already-authorized would otherwise
    block. Rejection caps are not what lets this stop through.
    """
    answers = tmp_path / "answers-current-pause.json"
    recorded = json.loads(RECORDED_ANSWERS.read_text())[DEFERRED]
    recorded["asks_permission_already_given"] = {"noul": 0.9, "type": "noul"}
    recorded["user_withheld_action"] = {"noul": 0.9, "type": "noul"}
    recorded["closing_asks_user_preference"] = NEUTRAL_NOUL
    answers.write_text(json.dumps(recorded))
    use_fake_judge(monkeypatch, str(answers))
    transcript = tmp_path / "older-goal-still-open.txt"
    transcript.write_text(
        'A session-scoped Stop hook is now active with condition: "finish the unfinished goal".\n'
        "\n"
        "Go ahead and finish the unfinished goal.\n"
    )
    payload = {
        "session_id": "hgtest-pause-wins",
        "hook_event_name": "Stop",
        "reason": "end_turn",
        "turn_number": "3",
        "transcript_path": str(transcript),
        "last_assistant_message": (
            "Paused. The older goal is still unfinished. "
            "Nothing else runs until you say resume."
        ),
    }

    run = state.run_payload(PY_HOOK, payload)

    assert_clean_run(run)
    assert decision_shape(run) == ALLOW, run.stdout
    assert run.log.endswith("\tallow\ttypesafe-allow\n")
    [entry] = judgments(state)
    assert (entry["path"], entry["block_kind"], entry["decision"]) == (
        "typesafe",
        "none",
        "no-objection",
    )
    assert not list(state.state_dir.glob("goal-handoff-*"))
    assert not list(state.state_dir.glob("goal-exhausted-*"))
    assert not list(state.state_dir.glob("stop-reject-*"))


def test_unproven_claim_blocks(
    state: HookSession, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    replay(monkeypatch, tmp_path, UNPROVEN)

    run = state.run_fixture(PY_HOOK, "completion-no-claim-allow.json")

    assert_clean_run(run)
    assert decision_shape(run) == BLOCK, run.stdout
    assert "found nothing this turn that backs it" in run.output["reason"]


# --- 3. TypeSafe can't answer: the stop is allowed ---------------------------------


@pytest.mark.parametrize("mode", [TYPESAFE_UNAVAILABLE, "crash", "hang", "garbage"])
@pytest.mark.parametrize("fixture", [H5_QUESTION_FIXTURE, H5_BENIGN_FIXTURE])
def test_typesafe_failure_allows_the_stop(
    state: HookSession, monkeypatch: pytest.MonkeyPatch, mode: str, fixture: str
) -> None:
    """No answer or a non-200 from TypeSafe never blocks: a guess is worse than no judge."""
    use_fake_judge(monkeypatch, mode)

    run: HookRun = state.run_fixture(PY_HOOK, fixture, TIMEOUT_ENV)

    assert_clean_run(run)
    assert decision_shape(run) == ALLOW, run.stdout
    [entry] = judgments(state)
    assert entry["path"] == "unavailable"
    assert entry["fallback_reason"]
    assert entry["decision"] == "no-objection"


def test_unavailable_judgment_records_every_failed_hop(
    state: HookSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The log must say why the hosted hop failed, not only the last hop's error."""
    use_fake_judge(monkeypatch, "unavailable-multihop")

    run: HookRun = state.run_fixture(PY_HOOK, H5_BENIGN_FIXTURE, TIMEOUT_ENV)

    assert_clean_run(run)
    [entry] = judgments(state)
    assert entry["fallback_reason"] == (
        "typesafe-unavailable:http 400 [api.typesafe.ai http 429 > localhost http 400]"
    )


def test_judgment_log_records_the_request_and_response_sent_to_typesafe(
    state: HookSession, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    replay(monkeypatch, tmp_path, DEFERRED)

    assert_clean_run(state.run_fixture(PY_HOOK, H5_BENIGN_FIXTURE))

    [entry] = judgments(state)
    assert set(entry["request"]) >= {"message", "user_prompt", "history", "evidence"}
    assert entry["response"]["action"] == "block"
    assert entry["response"]["source"] == "typesafe"
