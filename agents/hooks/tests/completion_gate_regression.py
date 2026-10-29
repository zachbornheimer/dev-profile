"""The completion gate must stay strong where the ask is known.

Pins the boundary the misfire replay introduces, on both enforcement points:

  judge policy (turn_judge.decide_turn)
    action ask   -> a deferral still blocks
    mixed ask    -> the deferred action clause still blocks
    known ask + invalid ```evidence fence on a completion claim -> H1 blocks
    no ask + the same claim                        -> vetoed, allow
  gate facade (completion_gate_turn_judge.TurnJudge)
    no user_prompt + a judged deferred block       -> downgraded to allow
    user_prompt present + the same judged block    -> passes through

Run:  python3 completion_gate_regression.py    # exit 0 when every case holds
"""

from __future__ import annotations

import importlib
import json
import subprocess
import sys
from pathlib import Path

TYPESAFE_SCRIPTS = (
    Path.home() / ".agents" / "available-skills" / "typesafe-ai" / "scripts"
)
HOOKS_LIB = Path.home() / ".agents" / "hooks" / "lib"
for _path in (str(TYPESAFE_SCRIPTS), str(HOOKS_LIB)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

turn_judge = importlib.import_module("turn_judge")
completion_gate_turn_judge = importlib.import_module("completion_gate_turn_judge")

NO_EVIDENCE = {"unmatched_test_failures": [], "evidence_block": {"present": False}}
INVALID_EVIDENCE = {
    "unmatched_test_failures": [],
    "evidence_block": {
        "present": True,
        "valid": False,
        "problem": "scope (must be one of: unit|live)",
        "type": "file",
        "ref": "/tmp/report.md",
    },
}
ACTION_ASK = "Fix the login redirect bug and run the tests."
MIXED_ASK = (
    "Advise me on the review syntax for PR #9; if the range looks right, "
    "run the review and report the findings."
)


def noul(value: float) -> dict:
    return {"type": "noul", "noul": value}


def score(p0: float, p1: float, p2: float) -> dict:
    return {
        "type": "score",
        "score": p1 + 2 * p2,
        "confidence": 0.9,
        "probabilities": {"0": p0, "1": p1, "2": p2},
    }


def deferral_answers() -> dict:
    """\"Reply go and I'll run it\" — every deferral path hot."""
    return {
        turn_judge.QUESTION_ENDS_ON_HANDOFF: noul(0.95),
        turn_judge.QUESTION_TURN_OUTCOME: score(0.02, 0.03, 0.95),
        turn_judge.QUESTION_DEFERS_DOABLE_WORK: noul(0.85),
        turn_judge.QUESTION_STOPPED_INVESTIGATION: noul(0.2),
        turn_judge.QUESTION_CLAIMS_COMPLETION: noul(0.05),
        turn_judge.QUESTION_UNPROVEN_CLAIM: noul(0.1),
        turn_judge.QUESTION_LEAVES_DOABLE_WORK: noul(0.85),
        turn_judge.QUESTION_REMAINING_WORK_RUNNING: noul(0.05),
        turn_judge.QUESTION_PREWORK_BEFORE_HANDOFF: noul(0.1),
        turn_judge.QUESTION_ASKS_PERMISSION_ALREADY_GIVEN: noul(0.05),
        turn_judge.QUESTION_USER_WITHHELD_ACTION: noul(0.05),
        turn_judge.QUESTION_CLOSING_ASKS_PREFERENCE: noul(0.05),
    }


def claim_answers() -> dict:
    """\"Done and verified\" with an invalid ```evidence fence."""
    return {
        turn_judge.QUESTION_ENDS_ON_HANDOFF: noul(0.1),
        turn_judge.QUESTION_TURN_OUTCOME: score(0.98, 0.01, 0.01),
        turn_judge.QUESTION_DEFERS_DOABLE_WORK: noul(0.05),
        turn_judge.QUESTION_STOPPED_INVESTIGATION: noul(0.05),
        turn_judge.QUESTION_CLAIMS_COMPLETION: noul(0.9),
        turn_judge.QUESTION_UNPROVEN_CLAIM: noul(0.85),
        turn_judge.QUESTION_LEAVES_DOABLE_WORK: noul(0.1),
        turn_judge.QUESTION_REMAINING_WORK_RUNNING: noul(0.9),
        turn_judge.QUESTION_PREWORK_BEFORE_HANDOFF: noul(0.05),
        turn_judge.QUESTION_ASKS_PERMISSION_ALREADY_GIVEN: noul(0.05),
        turn_judge.QUESTION_USER_WITHHELD_ACTION: noul(0.05),
        turn_judge.QUESTION_CLOSING_ASKS_PREFERENCE: noul(0.05),
    }


def case_action_ask_still_blocks() -> tuple[bool, str]:
    verdict = turn_judge.decide_turn(
        deferral_answers(), NO_EVIDENCE, None, user_request=ACTION_ASK
    )
    return (
        verdict.action == turn_judge.ACTION_BLOCK
        and verdict.block_kind == turn_judge.BLOCK_DEFERRED,
        f"{verdict.action}/{verdict.block_kind}",
    )


def case_mixed_ask_still_blocks() -> tuple[bool, str]:
    verdict = turn_judge.decide_turn(
        deferral_answers(), NO_EVIDENCE, None, user_request=MIXED_ASK
    )
    return (
        verdict.action == turn_judge.ACTION_BLOCK
        and verdict.block_kind == turn_judge.BLOCK_DEFERRED,
        f"{verdict.action}/{verdict.block_kind}",
    )


def case_h1_with_known_ask_still_blocks() -> tuple[bool, str]:
    verdict = turn_judge.decide_turn(
        claim_answers(), INVALID_EVIDENCE, None, user_request="Ship it"
    )
    return (
        verdict.action == turn_judge.ACTION_BLOCK
        and verdict.block_kind == turn_judge.BLOCK_INVALID_EVIDENCE_BLOCK,
        f"{verdict.action}/{verdict.block_kind}",
    )


def case_h1_without_ask_is_vetoed() -> tuple[bool, str]:
    verdict = turn_judge.decide_turn(
        claim_answers(), INVALID_EVIDENCE, None, user_request=""
    )
    return (
        verdict.action == turn_judge.ACTION_ALLOW
        and verdict.block_kind == turn_judge.BLOCK_NONE,
        f"{verdict.action}/{verdict.block_kind}",
    )


def _stub_judge_returning_deferred_block() -> completion_gate_turn_judge.TurnJudge:
    verdict = {
        "action": "block",
        "block_kind": "deferred",
        "source": "typesafe",
        "reason": "judged",
        "signals": {"leaves_doable_work": 0.95},
        "answers": {},
    }

    def run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            cmd, 0, stdout=json.dumps(verdict), stderr=""
        )

    return completion_gate_turn_judge.TurnJudge(
        cli=completion_gate_turn_judge.TYPESAFE_CLI, timeout_secs=5, run=run
    )


def case_facade_vetoes_deferral_without_ask() -> tuple[bool, str]:
    judgment = _stub_judge_returning_deferred_block().judge(
        {
            "message": "Run that from this worktree.",
            "user_prompt": "",
            "history": [],
            "evidence": {},
        }
    )
    return (
        not judgment.blocks
        and judgment.verdict.get("reason")
        == completion_gate_turn_judge.NO_ASK_CONTEXT_REASON,
        f"action={judgment.verdict.get('action')} reason={judgment.verdict.get('reason')}",
    )


def case_facade_passes_deferral_with_ask() -> tuple[bool, str]:
    judgment = _stub_judge_returning_deferred_block().judge(
        {
            "message": "I'll run it now.",
            "user_prompt": "Run the review.",
            "history": [],
            "evidence": {},
        }
    )
    return (judgment.blocks, f"blocks={judgment.blocks}")


CASES = (
    case_action_ask_still_blocks,
    case_mixed_ask_still_blocks,
    case_h1_with_known_ask_still_blocks,
    case_h1_without_ask_is_vetoed,
    case_facade_vetoes_deferral_without_ask,
    case_facade_passes_deferral_with_ask,
)


def main() -> int:
    failures = 0
    for case in CASES:
        ok, detail = case()
        print(f"{'PASS' if ok else 'FAIL'}  {case.__name__}: {detail}")
        failures += 0 if ok else 1
    print(f"{len(CASES) - failures}/{len(CASES)} boundary cases hold")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
