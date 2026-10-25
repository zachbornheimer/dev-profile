"""TypeSafe's judgment of a Stop, behind one facade.

``TurnJudge.judge`` runs ``typesafe.py judge-turn`` as a subprocess and
returns its verdict — or, when TypeSafe is missing, slow, or broken, a
judgment that says so, and completion-gate allows the stop.
The policy (thresholds, which answers block) lives in the TypeSafe skill's
turn_judge.py; this side only asks, explains a block, and logs. It still
enforces one rule consumer-side: a turn with no user_prompt (a subagent's
turn, or a transcript the hook could not read) is never blocked — see
``_veto_without_ask_context``.

Every judgment, from either path, is appended to
``<state_dir>/completion-gate-judgments.jsonl`` so thresholds can be tuned
from real outcomes.
"""

from __future__ import annotations

import contextlib
import json
import os
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from completion_gate_evidence import EVIDENCE_TEMPLATE, invalid_evidence_block_reason
from typesafe_location import TYPESAFE_CLI

TURN_JUDGE_CLI_ENV = "HC_TURN_JUDGE_CLI"
TURN_JUDGE_TIMEOUT_ENV = "HC_TURN_JUDGE_TIMEOUT_SECS"
DEFAULT_TIMEOUT_SECS = 9.0
JUDGE_TURN_ARGS = ("judge-turn", "--json")
JUDGMENTS_LOG_NAME = "completion-gate-judgments.jsonl"
SOURCE_TYPESAFE = "typesafe"
PATH_TYPESAFE = "typesafe"
PATH_UNAVAILABLE = "unavailable"
ACTION_BLOCK = "block"
ACTION_ALLOW = "allow"
CLOSING_LINE_CHARS = 200
MILLIS_PER_SECOND = 1000

BLOCK_DEFERRED = "deferred"
BLOCK_INVALID_EVIDENCE_BLOCK = "invalid_evidence_block"
BLOCK_ALREADY_AUTHORIZED = "already_authorized"
NO_ASK_CONTEXT_REASON = "vetoed-no-ask-context"
OFFERED_WORK_REASON = (
    'You stopped to wait for the user, but you can do the work you offered now: "{closing}" '
    "(TypeSafe: offered work doable now {defers_doable_work:.2f}). Do it now, then report the result. "
    "If you offered several options, do every one that doesn't need the user, not just the cheapest. "
    "Keep asking any genuine question (information only the user has, a scope decision, credentials, "
    "a destructive step with no undo) in the same turn; don't wait on it for work that doesn't depend on the answer."
)
UNINVESTIGATED_REASON = (
    "You stopped to wait for the user, but you left a failure or unclear cause you can investigate yourself: "
    '"{closing}" (TypeSafe: investigation left undone {stopped_investigation:.2f}). Do it now: dig in '
    "with your tools, then report what you found. Keep asking any genuine question in the same turn."
)
LEAVES_DOABLE_WORK_REASON = (
    'You mentioned work you can still do now: "{closing}" (TypeSafe: leftover doable work '
    "{leaves_doable_work:.2f}). Do it, then report. Ask the user only for what truly needs them, "
    "after the work is done."
)
ALREADY_AUTHORIZED_REASON = (
    'You stopped to ask for a go-ahead you already have: "{closing}" '
    "(TypeSafe: permission already given {asks_permission_already_given:.2f}). "
    "If that covers this action, do it now and report the result. If it covers only part of it, "
    "do that part and ask only about the rest, naming what the user's message did not cover."
)
PREWORK_REASON = (
    'This turn hands off to the user, but a person would want more done first: "{closing}" '
    "(TypeSafe: prep left undone {prework_before_handoff:.2f}). Before asking: research the answer "
    "or verify the facts with your tools, run the reversible checks, weigh the options, draft the "
    "command or answer, and lead with your recommended default. Then ask only for what nobody but "
    "the user holds, in a form they can answer in one line."
)
UNPROVEN_CLAIM_REASON = (
    "This turn claims the work is done, fixed, passing, or verified, but TypeSafe found nothing "
    "this turn that backs it (unproven claim {unproven_claim:.2f}): no test or command output and "
    "no subagent report. Run the check and cite its output, or downgrade the claim (e.g. 'not yet "
    "verified'). An evidence block also works:\n"
)

Run = Callable[..., subprocess.CompletedProcess[str]]


@dataclass(frozen=True, slots=True)
class TurnJudgment:
    """TypeSafe's verdict, or why there is none (``fallback_reason``)."""

    verdict: dict[str, Any] = field(default_factory=dict)
    fallback_reason: str = ""
    duration_ms: float = 0.0

    @property
    def decided(self) -> bool:
        return not self.fallback_reason

    @property
    def blocks(self) -> bool:
        return self.decided and self.verdict.get("action") == ACTION_BLOCK

    @property
    def block_kind(self) -> str:
        return str(self.verdict.get("block_kind") or "")

    @property
    def signals(self) -> dict[str, float]:
        signals = self.verdict.get("signals")
        return signals if isinstance(signals, dict) else {}


@dataclass(frozen=True, slots=True)
class TurnJudge:
    """Asks ``typesafe.py judge-turn``; never raises for a TypeSafe-side failure."""

    cli: Path
    timeout_secs: float
    run: Run = subprocess.run

    @classmethod
    def from_env(cls) -> TurnJudge:
        override = os.environ.get(TURN_JUDGE_CLI_ENV, "")
        cli = Path(override) if override else TYPESAFE_CLI
        return cls(cli, _timeout_from_env())

    def judge(self, envelope: dict[str, Any]) -> TurnJudgment:
        if not self.cli.is_file():
            return TurnJudgment(fallback_reason=f"cli-missing:{self.cli}")
        started = time.monotonic()
        reason, verdict = self._ask(envelope)
        verdict = _veto_without_ask_context(verdict, envelope)
        elapsed = round((time.monotonic() - started) * MILLIS_PER_SECOND, 1)
        return TurnJudgment(
            verdict=verdict, fallback_reason=reason, duration_ms=elapsed
        )

    def _ask(self, envelope: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        try:
            done = self.run(
                [sys.executable, str(self.cli), *JUDGE_TURN_ARGS],
                input=json.dumps(envelope),
                capture_output=True,
                text=True,
                timeout=self.timeout_secs,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return f"timeout-{self.timeout_secs:g}s", {}
        except OSError as exc:
            return f"cli-error:{type(exc).__name__}", {}
        if done.returncode != 0:
            return f"cli-exit-{done.returncode}", {}
        try:
            verdict = json.loads(done.stdout)
        except ValueError:
            return "cli-output-not-json", {}
        if not isinstance(verdict, dict):
            return "cli-output-not-object", {}
        if verdict.get("source") != SOURCE_TYPESAFE:
            hops = verdict.get("detail")
            suffix = f" [{hops}]" if hops else ""
            return f"typesafe-unavailable:{verdict.get('reason') or 'unknown'}{suffix}", verdict
        return "", verdict


def _timeout_from_env() -> float:
    with contextlib.suppress(ValueError):
        value = float(os.environ.get(TURN_JUDGE_TIMEOUT_ENV, ""))
        if value > 0:
            return value
    return DEFAULT_TIMEOUT_SECS


def _has_ask_context(envelope: dict[str, Any]) -> bool:
    """True when the envelope carries the user's request for this turn."""
    return bool(str(envelope.get("user_prompt") or "").strip())


def _veto_without_ask_context(
    verdict: dict[str, Any], envelope: dict[str, Any]
) -> dict[str, Any]:
    """Downgrade any block on a turn the judge could not see an ask for.

    The judge CLI is overridable (``HC_TURN_JUDGE_CLI``) and may predate the
    ask-context policy in the TypeSafe skill's turn_judge.py, so the consumer
    enforces the same rule: with no ``user_prompt`` there is no ask to leave
    work against — a subagent's parent owns both the ask and the audit, and a
    block here eats the subagent's final message instead of teaching anyone.
    Mirrors ``turn_judge._ask_is_known``; keep the two consistent.
    """
    if verdict.get("action") != ACTION_BLOCK or _has_ask_context(envelope):
        return verdict
    return {**verdict, "action": ACTION_ALLOW, "reason": NO_ASK_CONTEXT_REASON}


def request_state(envelope: dict[str, Any]) -> dict[str, Any]:
    """The exact `state` object TypeSafe judged, for the judgment log."""
    return {
        "final_message": envelope.get("message"),
        "user_request": envelope.get("user_prompt"),
        "history": envelope.get("history"),
        "evidence": envelope.get("evidence"),
    }


def _is_fence_only(line: str) -> bool:
    """True for a markdown fence opener/closer with no other content.

    TypeSafe often scores a turn that *ends* on a code fence (verify commands,
    JSON dumps, ```evidence) as deferred investigation. Quoting the bare fence
    as the closing line makes the block look like an FP ("```" @ 0.70). Skip
    fence-only lines when picking what the agent reads.
    """
    stripped = line.strip()
    if not stripped.startswith("```"):
        return False
    # ``` / ```json / ```evidence / ```go — the info string may follow
    rest = stripped[3:].strip()
    return " " not in rest and "\n" not in rest


def closing_line(message: str) -> str:
    lines = [line.strip() for line in message.strip().splitlines() if line.strip()]
    while lines and _is_fence_only(lines[-1]):
        lines.pop()
    last = lines[-1] if lines else ""
    return last if len(last) <= CLOSING_LINE_CHARS else last[:CLOSING_LINE_CHARS] + "…"


def block_reason(
    judgment: TurnJudgment,
    message: str,
    evidence_problem: str,
) -> str:
    """What the agent reads when TypeSafe's verdict blocks: what was seen, and what to do."""
    signals = {
        "defers_doable_work": 0.0,
        "stopped_investigation": 0.0,
        "unproven_claim": 0.0,
        "leaves_doable_work": 0.0,
        "prework_before_handoff": 0.0,
        "asks_permission_already_given": 0.0,
        **judgment.signals,
    }
    kind = judgment.block_kind
    if kind == BLOCK_ALREADY_AUTHORIZED:
        return ALREADY_AUTHORIZED_REASON.format(
            closing=closing_line(message), **signals
        )
    if kind == BLOCK_DEFERRED:
        return _deferred_reason(judgment.signals, signals, closing_line(message))
    if kind == BLOCK_INVALID_EVIDENCE_BLOCK:
        return invalid_evidence_block_reason(evidence_problem)
    return UNPROVEN_CLAIM_REASON.format(**signals) + EVIDENCE_TEMPLATE


def _deferred_reason(
    raw_signals: dict[str, float], signals: dict[str, float], closing: str
) -> str:
    """Name the undone work the stronger signal points at.

    ``raw_signals`` (unpadded with defaults) tells which path fired: the
    leaves-doable-work path only runs, and only adds its keys, when the
    handoff path already found nothing to block on.
    """
    if "prework_before_handoff" in raw_signals:
        return PREWORK_REASON.format(closing=closing, **signals)
    if "leaves_doable_work" in raw_signals:
        return LEAVES_DOABLE_WORK_REASON.format(closing=closing, **signals)
    if signals["stopped_investigation"] > signals["defers_doable_work"]:
        return UNINVESTIGATED_REASON.format(closing=closing, **signals)
    return OFFERED_WORK_REASON.format(closing=closing, **signals)


@dataclass(frozen=True, slots=True)
class JudgmentLog:
    """Append-only JSONL of every Stop judgment; a write failure is never fatal."""

    path: Path

    @classmethod
    def in_state_dir(cls, state_dir: Path) -> JudgmentLog:
        return cls(state_dir / JUDGMENTS_LOG_NAME)

    def record(self, entry: dict[str, Any]) -> None:
        with contextlib.suppress(OSError, TypeError, ValueError):
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry, sort_keys=True) + "\n")
