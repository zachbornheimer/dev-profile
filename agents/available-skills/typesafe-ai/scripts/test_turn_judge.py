"""judge-turn: question set, policy (decide_turn), and CLI fail-open. No network."""

from __future__ import annotations

import importlib
import io
import json
import sys
import unittest
import urllib.error
from pathlib import Path
from typing import Self
from unittest import mock

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

constants = importlib.import_module("constants")
turn_judge = importlib.import_module("turn_judge")
typesafe = importlib.import_module("typesafe")

SECRET = "test-key-not-for-logs"
QUESTIONS = (
    turn_judge.QUESTION_ENDS_ON_HANDOFF,
    turn_judge.QUESTION_DEFERS_DOABLE_WORK,
    turn_judge.QUESTION_STOPPED_INVESTIGATION,
    turn_judge.QUESTION_TURN_OUTCOME,
    turn_judge.QUESTION_CLAIMS_COMPLETION,
    turn_judge.QUESTION_UNPROVEN_CLAIM,
    turn_judge.QUESTION_LEAVES_DOABLE_WORK,
    turn_judge.QUESTION_REMAINING_WORK_RUNNING,
    turn_judge.QUESTION_PREWORK_BEFORE_HANDOFF,
    turn_judge.QUESTION_ASKS_PERMISSION_ALREADY_GIVEN,
    turn_judge.QUESTION_USER_WITHHELD_ACTION,
    turn_judge.QUESTION_CLOSING_ASKS_PREFERENCE,
)
NO_EVIDENCE: dict = {
    "unmatched_test_failures": [],
    "evidence_block": {"present": False},
}


def noul(value: float) -> dict:
    return {"type": "noul", "noul": value}


def score(p0: float, p1: float, p2: float, confidence: float = 0.9) -> dict:
    return {
        "type": "score",
        "score": p1 + 2 * p2,
        "confidence": confidence,
        "probabilities": {"0": p0, "1": p1, "2": p2},
        "legend": {"0": "level text echoed back"},
    }


def answers(
    *,
    handoff: float = 0.95,
    outcome: tuple[float, float, float] = (0.02, 0.03, 0.95),
    doable: float = 0.85,
    investigation: float = 0.2,
    claims: float = 0.05,
    unproven: float = 0.1,
    leaves: float = 0.1,
    running: float = 0.9,
    prework: float = 0.1,
    authorized: float = 0.05,
    withheld: float = 0.05,
    preference: float = 0.05,
) -> dict:
    """Defaults describe a deferred turn: 'reply "go" and I'll run it'."""
    return {
        turn_judge.QUESTION_ENDS_ON_HANDOFF: noul(handoff),
        turn_judge.QUESTION_TURN_OUTCOME: score(*outcome),
        turn_judge.QUESTION_DEFERS_DOABLE_WORK: noul(doable),
        turn_judge.QUESTION_STOPPED_INVESTIGATION: noul(investigation),
        turn_judge.QUESTION_CLAIMS_COMPLETION: noul(claims),
        turn_judge.QUESTION_UNPROVEN_CLAIM: noul(unproven),
        turn_judge.QUESTION_LEAVES_DOABLE_WORK: noul(leaves),
        turn_judge.QUESTION_REMAINING_WORK_RUNNING: noul(running),
        turn_judge.QUESTION_PREWORK_BEFORE_HANDOFF: noul(prework),
        turn_judge.QUESTION_ASKS_PERMISSION_ALREADY_GIVEN: noul(authorized),
        turn_judge.QUESTION_USER_WITHHELD_ACTION: noul(withheld),
        turn_judge.QUESTION_CLOSING_ASKS_PREFERENCE: noul(preference),
    }


FINISHED_OUTCOME = (0.98, 0.01, 0.01)
FINISHED = {"handoff": 0.1, "outcome": (0.98, 0.01, 0.01)}
CLAIM = {**FINISHED, "claims": 0.9}


class QuestionTests(unittest.TestCase):
    def test_one_request_carries_every_question(self) -> None:
        request = turn_judge.build_request(
            {"message": "Done.", "user_prompt": "fix it", "evidence": NO_EVIDENCE}
        )
        self.assertEqual(set(request["questions"]), set(QUESTIONS))
        self.assertEqual(request["state"]["final_message"], "Done.")
        self.assertEqual(request["state"]["user_request"], "fix it")
        self.assertEqual(request["state"]["evidence"], NO_EVIDENCE)

    def test_the_request_carries_the_earlier_exchanges(self) -> None:
        history = [
            {"user_request": "look at session 33eb", "response": "Two problems found."}
        ]
        request = turn_judge.build_request(
            {
                "message": "Done.",
                "user_prompt": "go",
                "history": history,
                "evidence": NO_EVIDENCE,
            }
        )
        self.assertEqual(request["state"]["history"], history)

    def test_every_question_is_a_plain_english_question(self) -> None:
        for key, question in turn_judge.build_questions().items():
            with self.subTest(key=key):
                self.assertTrue(question["instructions"].endswith("?"))
                self.assertGreater(len(question["instructions"].split()), 4)

    def test_score_levels_have_sentences_and_three_to_five_examples(self) -> None:
        levels = turn_judge.TURN_OUTCOME_LEVELS
        self.assertEqual(len(levels), 3)
        for level in levels:
            self.assertTrue(level["what"].endswith("."))
            self.assertTrue(3 <= len(level["examples"]) <= 5)

    def test_turn_outcome_examples_include_the_known_miss(self) -> None:
        deferred_examples = " ".join(
            turn_judge.TURN_OUTCOME_LEVELS[turn_judge.OUTCOME_DEFERRED_LEVEL][
                "examples"
            ]
        )
        self.assertIn("fix split now", deferred_examples)


class DecideTurnTests(unittest.TestCase):
    def decide(self, evidence: dict | None = None, **overrides: object) -> object:
        return turn_judge.decide_turn(
            answers(**overrides), evidence or NO_EVIDENCE, None, user_request="fix it"
        )

    def test_deferred_handoff_blocks(self) -> None:
        verdict = self.decide()
        self.assertEqual((verdict.action, verdict.block_kind), ("block", "deferred"))
        self.assertEqual(verdict.source, constants.SOURCE_TYPESAFE)
        self.assertEqual(verdict.signals["defers_doable_work"], 0.85)

    def test_finished_turn_allows_without_reading_deferral_answers(self) -> None:
        partial = answers(**FINISHED)
        del partial[turn_judge.QUESTION_DEFERS_DOABLE_WORK]
        del partial[turn_judge.QUESTION_STOPPED_INVESTIGATION]
        verdict = turn_judge.decide_turn(partial, NO_EVIDENCE)
        self.assertEqual(verdict.action, "allow")

    def test_uninvestigated_failure_blocks_without_offered_work(self) -> None:
        self.assertEqual(
            self.decide(doable=0.1, investigation=0.9).block_kind, "deferred"
        )

    def test_ask_with_nothing_doable_and_nothing_to_investigate_allows(self) -> None:
        self.assertEqual(
            self.decide(outcome=WAITS_ON_USER, doable=0.3, investigation=0.2).action,
            "allow",
        )

    def test_a_genuine_question_cannot_excuse_doable_work(self) -> None:
        """The real miss: reply "go" and I'll commit, plus a separate exit-code question."""
        verdict = self.decide(outcome=(0.02, 0.9, 0.08), doable=0.86)
        self.assertEqual(verdict.block_kind, "deferred")

    def test_thresholds_are_inclusive_at_the_bar(self) -> None:
        self.assertEqual(
            self.decide(
                doable=constants.TURN_DOABLE_WORK_THRESHOLD, investigation=0.0
            ).block_kind,
            "deferred",
        )
        self.assertEqual(
            self.decide(
                doable=0.0, investigation=constants.TURN_UNINVESTIGATED_THRESHOLD
            ).block_kind,
            "deferred",
        )

    def test_leftover_work_blocks_even_without_a_handoff(self) -> None:
        """'It's a ~10-minute add.' never frames itself as asking for a go-ahead."""
        verdict = self.decide(
            handoff=0.2, doable=0.1, investigation=0.1, leaves=0.9, running=0.08
        )
        self.assertEqual((verdict.action, verdict.block_kind), ("block", "deferred"))
        self.assertEqual(verdict.signals["leaves_doable_work"], 0.9)

    def test_leftover_work_already_running_in_background_allows(self) -> None:
        verdict = self.decide(
            outcome=FINISHED_OUTCOME,
            handoff=0.2,
            doable=0.1,
            investigation=0.1,
            leaves=0.9,
            running=0.9,
        )
        self.assertEqual(verdict.action, "allow")

    def test_leftover_work_below_threshold_allows(self) -> None:
        verdict = self.decide(
            outcome=FINISHED_OUTCOME,
            handoff=0.2,
            doable=0.1,
            investigation=0.1,
            leaves=0.5,
            running=0.0,
        )
        self.assertEqual(verdict.action, "allow")

    def test_leftover_work_thresholds_are_inclusive_at_the_bar(self) -> None:
        verdict = self.decide(
            handoff=0.2,
            doable=0.1,
            investigation=0.1,
            leaves=constants.TURN_LEAVES_DOABLE_WORK_THRESHOLD,
            running=constants.TURN_REMAINING_WORK_RUNNING_THRESHOLD - 0.01,
        )
        self.assertEqual(verdict.block_kind, "deferred")

    def test_unproven_claim_blocks(self) -> None:
        verdict = self.decide(**CLAIM, unproven=0.9)
        self.assertEqual(verdict.block_kind, "unproven_claim")

    def test_claim_with_evidence_allows(self) -> None:
        self.assertEqual(self.decide(**CLAIM, unproven=0.3).action, "allow")

    def test_corroborated_evidence_block_excuses_the_claim(self) -> None:
        evidence = {
            "unmatched_test_failures": [],
            "evidence_block": {"present": True, "valid": True, "corroborated": True},
        }
        self.assertEqual(self.decide(evidence, **CLAIM, unproven=0.95).action, "allow")

    def test_claim_with_unmatched_failure_blocks_first(self) -> None:
        evidence = {
            "unmatched_test_failures": ["TestX"],
            "evidence_block": {"present": False},
        }
        self.assertEqual(
            self.decide(evidence, **CLAIM, unproven=0.0).block_kind,
            "unmatched_failures",
        )

    def test_claim_with_malformed_evidence_block_blocks(self) -> None:
        evidence = {
            "unmatched_test_failures": [],
            "evidence_block": {"present": True, "valid": False},
        }
        self.assertEqual(
            self.decide(evidence, **CLAIM).block_kind, "invalid_evidence_block"
        )

    def test_unmatched_failure_without_a_claim_allows(self) -> None:
        evidence = {
            "unmatched_test_failures": ["TestX"],
            "evidence_block": {"present": False},
        }
        self.assertEqual(self.decide(evidence, **FINISHED).action, "allow")

    def test_logged_answers_drop_echoed_legends(self) -> None:
        verdict = self.decide()
        self.assertNotIn(
            "legend", verdict.as_json()["answers"][turn_judge.QUESTION_TURN_OUTCOME]
        )

    def test_malformed_answer_raises(self) -> None:
        broken = answers()
        broken[turn_judge.QUESTION_ENDS_ON_HANDOFF] = {"type": "noul", "noul": True}
        with self.assertRaises(TypeError):
            turn_judge.decide_turn(broken, NO_EVIDENCE)


WAITS_ON_USER = (0.03, 0.94, 0.03)
HANDS_OFF = (0.03, 0.03, 0.94)


class OutcomeGatingTests(unittest.TestCase):
    """Real turns from state/judgments.jsonl (2026-09-30): the outcome score was right, the policy ignored it."""

    def decide(self, **overrides: object) -> object:
        return turn_judge.decide_turn(
            answers(**overrides), NO_EVIDENCE, None, user_request="fix it"
        )

    def test_user_handed_over_the_turn_is_not_uninvestigated_work(self) -> None:
        """27c0e624: 'send the rest of what you have' after 'I'll provide more' was blocked at 0.83."""
        verdict = self.decide(
            outcome=WAITS_ON_USER,
            handoff=0.91,
            doable=0.77,
            investigation=0.83,
            leaves=0.69,
        )
        self.assertEqual(verdict.action, "allow")

    def test_question_only_the_user_can_answer_is_not_leftover_work(self) -> None:
        """33eb44f5 'answer question 3' and 81b793b8 'is this file synthetic?'."""
        verdict = self.decide(
            outcome=WAITS_ON_USER,
            handoff=0.2,
            doable=0.1,
            investigation=0.1,
            leaves=0.9,
            running=0.05,
        )
        self.assertEqual(verdict.action, "allow")

    def test_explicit_doable_offer_still_blocks_when_the_turn_also_waits(self) -> None:
        verdict = self.decide(outcome=WAITS_ON_USER, doable=0.9)
        self.assertEqual(verdict.block_kind, "deferred")

    def test_handing_the_user_a_command_the_agent_can_run_blocks(self) -> None:
        """fed60255 'Next, about 2 minutes on your Mac: cd ... && go build': allowed before."""
        verdict = self.decide(
            outcome=HANDS_OFF,
            handoff=0.3,
            doable=0.2,
            investigation=0.1,
            leaves=0.2,
            running=0.1,
        )
        self.assertEqual((verdict.action, verdict.block_kind), ("block", "deferred"))

    def test_hands_off_below_the_confidence_bar_allows(self) -> None:
        verdict = self.decide(
            outcome=(0.3, 0.1, 0.6),
            handoff=0.3,
            doable=0.2,
            investigation=0.1,
            leaves=0.2,
        )
        self.assertEqual(verdict.action, "allow")

    def test_waiting_turn_with_prep_left_undone_blocks(self) -> None:
        """The user's question: is there work to do before a person takes over?"""
        verdict = self.decide(outcome=WAITS_ON_USER, doable=0.2, prework=0.92)
        self.assertEqual((verdict.action, verdict.block_kind), ("block", "deferred"))
        self.assertEqual(verdict.signals["prework_before_handoff"], 0.92)

    def test_waiting_turn_that_did_its_prep_allows(self) -> None:
        self.assertEqual(
            self.decide(outcome=WAITS_ON_USER, doable=0.2, prework=0.3).action, "allow"
        )

    def test_prep_bar_is_inclusive(self) -> None:
        verdict = self.decide(
            outcome=WAITS_ON_USER, doable=0.2, prework=constants.TURN_PREWORK_THRESHOLD
        )
        self.assertEqual(verdict.block_kind, "deferred")

    def test_asking_for_a_go_ahead_the_user_already_gave_blocks(self) -> None:
        """18fa3bd1: 'reply push' after the user said 'Go ahead ... have a worker set up the repo'."""
        verdict = self.decide(outcome=WAITS_ON_USER, doable=0.2, authorized=0.9)
        self.assertEqual(
            (verdict.action, verdict.block_kind), ("block", "already_authorized")
        )
        self.assertEqual(verdict.signals["asks_permission_already_given"], 0.9)

    def test_already_authorized_outranks_the_deferred_paths(self) -> None:
        self.assertEqual(self.decide(authorized=0.9).block_kind, "already_authorized")

    def test_already_authorized_bar_is_inclusive(self) -> None:
        verdict = self.decide(
            outcome=WAITS_ON_USER,
            doable=0.2,
            authorized=constants.TURN_ALREADY_AUTHORIZED_THRESHOLD,
        )
        self.assertEqual(verdict.block_kind, "already_authorized")

    def test_a_standing_hold_off_instruction_excuses_the_deferral(self) -> None:
        verdict = self.decide(withheld=0.88)
        self.assertEqual((verdict.action, verdict.block_kind), ("allow", "none"))
        self.assertEqual(verdict.signals["user_withheld_action"], 0.88)

    def test_hold_off_bar_is_inclusive(self) -> None:
        self.assertEqual(
            self.decide(withheld=constants.TURN_USER_WITHHELD_THRESHOLD).action, "allow"
        )

    def test_a_weak_hold_off_signal_does_not_excuse_the_deferral(self) -> None:
        verdict = self.decide(withheld=constants.TURN_USER_WITHHELD_THRESHOLD - 0.01)
        self.assertEqual(verdict.block_kind, "deferred")

    def test_a_current_pause_wins_over_an_older_authorization(self) -> None:
        """The latest hold-off is still in force; an older grant does not revive the work."""
        verdict = self.decide(withheld=0.9, authorized=0.9)
        self.assertEqual((verdict.action, verdict.block_kind), ("allow", "none"))

    def test_an_excused_deferral_still_faces_the_completion_claim_check(self) -> None:
        verdict = self.decide(withheld=0.9, claims=0.9, unproven=0.95)
        self.assertEqual(verdict.block_kind, "unproven_claim")

    def test_a_closing_preference_question_excuses_the_deferral(self) -> None:
        verdict = self.decide(preference=0.97)
        self.assertEqual((verdict.action, verdict.block_kind), ("allow", "none"))
        self.assertEqual(verdict.signals["closing_asks_user_preference"], 0.97)

    def test_preference_bar_is_inclusive(self) -> None:
        self.assertEqual(
            self.decide(preference=constants.TURN_CLOSING_PREFERENCE_THRESHOLD).action,
            "allow",
        )

    def test_a_weak_preference_signal_does_not_excuse_the_deferral(self) -> None:
        verdict = self.decide(
            preference=constants.TURN_CLOSING_PREFERENCE_THRESHOLD - 0.01
        )
        self.assertEqual(verdict.block_kind, "deferred")

    def test_excuse_answers_are_not_read_for_a_finished_turn(self) -> None:
        partial = answers(**FINISHED)
        del partial[turn_judge.QUESTION_USER_WITHHELD_ACTION]
        del partial[turn_judge.QUESTION_CLOSING_ASKS_PREFERENCE]
        self.assertEqual(turn_judge.decide_turn(partial, NO_EVIDENCE).action, "allow")

    def test_the_hold_off_question_names_the_held_back_action_first(self) -> None:
        question = turn_judge.build_questions()[
            turn_judge.QUESTION_USER_WITHHELD_ACTION
        ]
        self.assertIn("identify the one action", question["instructions"])

    def test_outcome_answer_is_required(self) -> None:
        broken = answers()
        broken[turn_judge.QUESTION_TURN_OUTCOME] = noul(0.5)
        with self.assertRaises(ValueError):
            turn_judge.decide_turn(broken, NO_EVIDENCE)


class FakeHTTPResponse:
    def __init__(self, payload: dict) -> None:
        self._body = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        return None


def getenv_with_key(name: str, default: str | None = None) -> str | None:
    return SECRET if name == constants.API_KEY_ENV else default


def getenv_without_key(_name: str, default: str | None = None) -> str | None:
    return default


def run_cli(stdin: str, urlopen: mock.Mock, getenv: object = getenv_with_key) -> dict:
    out = io.StringIO()
    code = typesafe.main(
        ["judge-turn", "--json"],
        getenv=getenv,
        urlopen=urlopen,
        read_keychain=lambda: None,
        stdin=io.StringIO(stdin),
        stdout=out,
    )
    assert code == 0
    return json.loads(out.getvalue())


ENVELOPE = json.dumps(
    {"message": "Want me to fix it?", "user_prompt": "fix it", "evidence": NO_EVIDENCE}
)


class JudgeTurnCliTests(unittest.TestCase):
    def test_live_shaped_answers_block_a_deferral(self) -> None:
        urlopen = mock.Mock(
            return_value=FakeHTTPResponse(
                {"answers": answers(), "usage": {"input_tokens": 9}}
            )
        )
        result = run_cli(ENVELOPE, urlopen)
        self.assertEqual(
            (result["action"], result["block_kind"], result["source"]),
            ("block", "deferred", "typesafe"),
        )
        self.assertEqual(result["usage"], {"input_tokens": 9})
        self.assertEqual(
            urlopen.call_args.kwargs["timeout"],
            constants.TURN_JUDGE_REQUEST_TIMEOUT_SECONDS,
        )
        body = json.loads(urlopen.call_args.args[0].data.decode("utf-8"))
        self.assertEqual(set(body["questions"]), set(QUESTIONS))
        self.assertEqual(urlopen.call_count, 1)

    def test_missing_key_falls_back_without_calling(self) -> None:
        urlopen = mock.Mock()
        result = run_cli(ENVELOPE, urlopen, getenv=getenv_without_key)
        self.assertEqual(
            (result["source"], result["reason"]),
            ("fallback", constants.REASON_MISSING_KEY),
        )
        urlopen.assert_not_called()

    def test_timeout_falls_back(self) -> None:
        result = run_cli(ENVELOPE, mock.Mock(side_effect=TimeoutError("timed out")))
        self.assertEqual(
            (result["source"], result["reason"]), ("fallback", constants.REASON_TIMEOUT)
        )

    def test_failure_names_every_hop_in_detail_not_in_reason(self) -> None:
        def refused(code: int) -> urllib.error.HTTPError:
            return urllib.error.HTTPError(
                "http://x", code, "refused", {}, io.BytesIO(b"")
            )

        result = run_cli(ENVELOPE, mock.Mock(side_effect=[refused(429), refused(400)]))
        self.assertEqual(
            (result["source"], result["reason"], result["detail"]),
            ("fallback", "http 400", "api.typesafe.ai http 429 > localhost http 400"),
        )

    def test_detail_appears_only_when_a_request_failed(self) -> None:
        result = run_cli(ENVELOPE, mock.Mock(side_effect=TimeoutError("timed out")))
        self.assertEqual(
            result["detail"], "api.typesafe.ai timeout > localhost timeout"
        )
        self.assertNotIn(
            "detail", run_cli(ENVELOPE, mock.Mock(), getenv=getenv_without_key)
        )

    def test_malformed_answers_fall_back(self) -> None:
        result = run_cli(
            ENVELOPE, mock.Mock(return_value=FakeHTTPResponse({"answers": {}}))
        )
        self.assertEqual(result["source"], "fallback")
        self.assertIn("missing", result["reason"])

    def test_bad_envelope_falls_back(self) -> None:
        for stdin in ("not json", "[]", json.dumps({"message": "  "})):
            with self.subTest(stdin=stdin):
                self.assertEqual(run_cli(stdin, mock.Mock())["source"], "fallback")


class NoAskContextTests(unittest.TestCase):
    """No user_request — a subagent's turn — has no ask to leave work against."""

    NO_ASK_EVIDENCE: dict = {  # noqa: RUF012 — a read-only test fixture, never mutated
        "unmatched_test_failures": [],
        "evidence_block": {"present": True, "valid": False},
    }

    def finished_claim(self) -> dict:
        return {
            **answers(),
            turn_judge.QUESTION_TURN_OUTCOME: score(0.98, 0.01, 0.01),
            turn_judge.QUESTION_ENDS_ON_HANDOFF: noul(0.1),
            turn_judge.QUESTION_LEAVES_DOABLE_WORK: noul(0.1),
            turn_judge.QUESTION_CLAIMS_COMPLETION: noul(0.9),
            turn_judge.QUESTION_UNPROVEN_CLAIM: noul(0.85),
        }

    def test_deferral_without_ask_is_vetoed(self) -> None:
        verdict = turn_judge.decide_turn(answers(), NO_EVIDENCE, None, user_request="")
        self.assertEqual(
            (verdict.action, verdict.block_kind, verdict.source),
            (
                turn_judge.ACTION_ALLOW,
                turn_judge.BLOCK_NONE,
                turn_judge.SOURCE_TYPESAFE,
            ),
        )

    def test_vetoed_signals_stay_computed_for_the_log(self) -> None:
        verdict = turn_judge.decide_turn(
            answers(handoff=0.1, leaves=0.9), NO_EVIDENCE, None, user_request=""
        )
        self.assertGreaterEqual(
            verdict.signals["leaves_doable_work"],
            constants.TURN_LEAVES_DOABLE_WORK_THRESHOLD,
        )

    def test_deferral_with_ask_still_blocks(self) -> None:
        verdict = turn_judge.decide_turn(
            answers(), NO_EVIDENCE, None, user_request="fix it"
        )
        self.assertEqual(
            (verdict.action, verdict.block_kind),
            (turn_judge.ACTION_BLOCK, turn_judge.BLOCK_DEFERRED),
        )

    def test_invalid_evidence_block_with_ask_still_blocks(self) -> None:
        verdict = turn_judge.decide_turn(
            self.finished_claim(), self.NO_ASK_EVIDENCE, None, user_request="ship it"
        )
        self.assertEqual(verdict.block_kind, turn_judge.BLOCK_INVALID_EVIDENCE_BLOCK)

    def test_invalid_evidence_block_without_ask_is_vetoed(self) -> None:
        verdict = turn_judge.decide_turn(
            self.finished_claim(), self.NO_ASK_EVIDENCE, None, user_request=""
        )
        self.assertEqual(
            (verdict.action, verdict.block_kind),
            (turn_judge.ACTION_ALLOW, turn_judge.BLOCK_NONE),
        )

    def test_deferral_questions_exclude_user_addressed_instructions(self) -> None:
        questions = turn_judge.build_questions()
        for key in (
            turn_judge.QUESTION_ENDS_ON_HANDOFF,
            turn_judge.QUESTION_DEFERS_DOABLE_WORK,
            turn_judge.QUESTION_LEAVES_DOABLE_WORK,
        ):
            with self.subTest(question=key):
                self.assertIn(
                    "addressed to the user", questions[key]["criteria"]["true"]
                )
        deferred_level = turn_judge.TURN_OUTCOME_LEVELS[
            turn_judge.OUTCOME_DEFERRED_LEVEL
        ]["what"]
        self.assertIn("addressed to the user", deferred_level)


if __name__ == "__main__":
    unittest.main()
