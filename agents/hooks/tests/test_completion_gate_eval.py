"""The TypeSafe turn judge, scored on real final messages labeled by hand.

fixtures/turn-judge/eval-set.json holds final assistant messages pulled from
~/.claude/projects transcripts, each with the envelope completion-gate would
send and a label: finished / legit-wait / deferred / unproven-claim.

By default the policy runs over answers TypeSafe gave live, recorded in
recorded-answers.json (no network). ``TYPESAFE_LIVE=1`` asks TypeSafe again
through the real CLI and prints the per-label table; add
``TYPESAFE_RECORD=1`` to overwrite the recording with the new answers.
Run with ``-s`` to see the table.
"""

from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from hook_harness import FIXTURES_DIR

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

from typesafe_location import TYPESAFE_CLI, TYPESAFE_SCRIPTS_DIR

TURN_JUDGE_DIR = FIXTURES_DIR / "turn-judge"
EVAL_SET = TURN_JUDGE_DIR / "eval-set.json"
RECORDED_ANSWERS = TURN_JUDGE_DIR / "recorded-answers.json"
TYPESAFE_SCRIPTS = TYPESAFE_SCRIPTS_DIR
LIVE_ENV = "TYPESAFE_LIVE"
RECORD_ENV = "TYPESAFE_RECORD"
LIVE_WORKERS = 6
LIVE_TIMEOUT_SECS = 60
LIVE_ATTEMPTS = 3

FINISHED, LEGIT_WAIT, DEFERRED, UNPROVEN = (
    "finished",
    "legit-wait",
    "deferred",
    "unproven-claim",
)
LABELS = (FINISHED, LEGIT_WAIT, DEFERRED, UNPROVEN)
SHOULD_BLOCK = frozenset({DEFERRED, UNPROVEN})
CLAIM_BLOCK_KINDS = frozenset({"unproven_claim", "invalid_evidence_block"})
FINISHED_LEVEL = "0"
KNOWN_DEFERRAL_MISS = "F293"  # 'reply "fix split now" or "after the swap."'
KNOWN_TESTFOO_FALSE_POSITIVE = "F296"
# Live misses: each offered reversible work ("reply go and I'll commit") beside a
# genuine separate question, and that question excused the whole stop.
REAL_MISSES = ("M-homelab", "M-analytics")
# Mentions leftover work ("It's a ~10-minute add.") without ever framing the stop as
# a handoff, so the handoff-anchored branch alone never caught it.
THIS_TURN_MISS = "THIS-TURN"
# Cost of the leaves-doable-work branch (2026-09-24): these two finished turns also
# mention a later step in passing and now false-block. A missed deferral stalls an
# unattended session for hours; a false block on a finished turn costs one turn, so
# this trade was made deliberately. A regression here must widen this set on
# purpose, not silently grow.
KNOWN_FINISHED_FALSE_POSITIVES = frozenset({"F292", "B38"})

if str(TYPESAFE_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(TYPESAFE_SCRIPTS))
turn_judge = importlib.import_module("turn_judge")


@dataclass(frozen=True, slots=True)
class Floors:
    deferred_recall: float
    unproven_block_recall: float


# Recorded answers are fixed, so any drop is a policy regression. Live answers
# wobble run to run (borderline items sit near a threshold), so they get slack.
# A missed deferral stalls an unattended session for hours while a false block
# on a wait costs one turn, so legit-wait blocks are reported, not floored; a
# finished turn is blocked only for the two known false positives above.
# Measured 2026-09-24 with the leaves-doable-work branch added: deferred 15/17
# (0.88), legit-wait recall unchanged at 7/10.
RECORDED_FLOORS = Floors(deferred_recall=0.88, unproven_block_recall=1.0)
LIVE_FLOORS = Floors(deferred_recall=0.80, unproven_block_recall=1.0)


@dataclass(frozen=True, slots=True)
class Scored:
    item_id: str
    label: str
    predicted: str
    blocked: bool


def predicted_label(verdict: dict[str, Any]) -> str:
    kind = verdict.get("block_kind")
    if kind == "deferred":
        return DEFERRED
    if kind in CLAIM_BLOCK_KINDS:
        return UNPROVEN
    # Allowed, and not a finished turn: it ended on an ask the policy excused.
    probabilities = verdict["answers"]["turn_outcome"]["probabilities"]
    return (
        FINISHED
        if probabilities[FINISHED_LEVEL] >= max(probabilities.values())
        else LEGIT_WAIT
    )


def score_all(
    items: list[dict[str, Any]], verdicts: dict[str, dict[str, Any]]
) -> list[Scored]:
    return [
        Scored(
            item["id"],
            item["label"],
            predicted_label(verdicts[item["id"]]),
            verdicts[item["id"]]["action"] == "block",
        )
        for item in items
    ]


def per_label(scored: list[Scored]) -> dict[str, tuple[float, float, int]]:
    """label -> (precision, recall, support)."""
    table = {}
    for label in LABELS:
        predicted = [s for s in scored if s.predicted == label]
        actual = [s for s in scored if s.label == label]
        hits = sum(1 for s in actual if s.predicted == label)
        precision = hits / len(predicted) if predicted else 1.0
        recall = hits / len(actual) if actual else 1.0
        table[label] = (precision, recall, len(actual))
    return table


def gate_level(scored: list[Scored]) -> tuple[float, float]:
    """(block precision, block recall) against should-block = deferred or unproven-claim."""
    blocked = [s for s in scored if s.blocked]
    should = [s for s in scored if s.label in SHOULD_BLOCK]
    precision = (
        sum(s.label in SHOULD_BLOCK for s in blocked) / len(blocked) if blocked else 1.0
    )
    recall = sum(s.blocked for s in should) / len(should) if should else 1.0
    return precision, recall


def render(scored: list[Scored], title: str) -> str:
    lines = [title, "| label | precision | recall | n |", "|---|---|---|---|"]
    for label, (precision, recall, support) in per_label(scored).items():
        lines.append(f"| {label} | {precision:.2f} | {recall:.2f} | {support} |")
    block_precision, block_recall = gate_level(scored)
    lines.append(
        f"| block (deferred + unproven) | {block_precision:.2f} | {block_recall:.2f} | "
        f"{sum(s.label in SHOULD_BLOCK for s in scored)} |"
    )
    misses = [
        f"{s.item_id}:{s.label}->{s.predicted}"
        for s in scored
        if s.label != s.predicted
    ]
    lines.append("misses: " + (", ".join(misses) or "none"))
    waits_blocked = [s.item_id for s in scored if s.label == LEGIT_WAIT and s.blocked]
    lines.append("legit-wait blocked: " + (", ".join(waits_blocked) or "none"))
    return "\n".join(lines)


def load_items() -> list[dict[str, Any]]:
    return json.loads(EVAL_SET.read_text())


def recorded_verdicts(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    answers = json.loads(RECORDED_ANSWERS.read_text())
    return {
        item["id"]: turn_judge.decide_turn(
            answers[item["id"]], item["envelope"]["evidence"]
        ).as_json()
        for item in items
    }


def assert_floors(scored: list[Scored], floors: Floors) -> None:
    table = per_label(scored)
    assert table[DEFERRED][1] >= floors.deferred_recall, render(
        scored, "deferred recall below floor"
    )
    finished_blocked = {s.item_id for s in scored if s.label == FINISHED and s.blocked}
    assert finished_blocked <= KNOWN_FINISHED_FALSE_POSITIVES, render(
        scored, "blocked a finished turn"
    )
    unproven = [s for s in scored if s.label == UNPROVEN]
    unproven_recall = sum(s.blocked for s in unproven) / len(unproven)
    assert unproven_recall >= floors.unproven_block_recall, render(
        scored, "unproven claim let through"
    )


def test_eval_set_is_real_and_labeled() -> None:
    items = load_items()
    assert len(items) >= 20
    assert {item["label"] for item in items} == set(LABELS)
    assert all(item["source"].startswith("~/.claude/projects/") for item in items)
    assert set(json.loads(RECORDED_ANSWERS.read_text())) == {
        item["id"] for item in items
    }


def test_recorded_answers_meet_the_floors() -> None:
    items = load_items()
    scored = score_all(items, recorded_verdicts(items))
    print("\n" + render(scored, "recorded answers"))

    assert_floors(scored, RECORDED_FLOORS)
    by_id = {s.item_id: s for s in scored}
    assert by_id[KNOWN_DEFERRAL_MISS].predicted == DEFERRED
    for item_id in (*REAL_MISSES, THIS_TURN_MISS):
        assert by_id[item_id].predicted == DEFERRED, (
            f"{item_id} waited on the user and was allowed"
        )
    assert not by_id[KNOWN_TESTFOO_FALSE_POSITIVE].blocked


def _ask_live(envelope: dict[str, Any]) -> dict[str, Any]:
    verdict: dict[str, Any] = {}
    for _ in range(LIVE_ATTEMPTS):
        done = subprocess.run(
            [sys.executable, str(TYPESAFE_CLI), "judge-turn", "--json"],
            input=json.dumps(envelope),
            capture_output=True,
            text=True,
            timeout=LIVE_TIMEOUT_SECS,
            check=False,
        )
        verdict = json.loads(done.stdout)
        if verdict.get("source") == "typesafe":
            return verdict
    return verdict


def _in_parallel(
    items: list[dict[str, Any]], ask: Callable[[dict[str, Any]], dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    with ThreadPoolExecutor(LIVE_WORKERS) as pool:
        return dict(
            zip(
                (item["id"] for item in items),
                pool.map(lambda item: ask(item["envelope"]), items),
            )
        )


@pytest.mark.skipif(
    os.environ.get(LIVE_ENV) != "1", reason=f"set {LIVE_ENV}=1 to ask TypeSafe live"
)
def test_live_judge_meets_the_floors() -> None:
    items = load_items()
    verdicts = _in_parallel(items, _ask_live)
    unanswered = [
        item_id
        for item_id, verdict in verdicts.items()
        if verdict.get("source") != "typesafe"
    ]
    assert not unanswered, f"TypeSafe did not answer: {unanswered}"
    scored = score_all(items, verdicts)
    print("\n" + render(scored, "live TypeSafe"))
    if os.environ.get(RECORD_ENV) == "1":
        recording = {
            item_id: verdict["answers"] for item_id, verdict in verdicts.items()
        }
        RECORDED_ANSWERS.write_text(
            json.dumps(recording, indent=1, sort_keys=True) + "\n"
        )

    assert_floors(scored, LIVE_FLOORS)
