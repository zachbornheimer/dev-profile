#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Stop hook — H1 (evidence-before-completion-claims) + H5 (no permission-
asking questions on already-authorized work).

Input (stdin, JSON): session_id, transcript_path, last_assistant_message,
turn_number, hook_event_name. Docs: https://code.claude.com/docs/en/hooks

Order of checks, each able to end the decision: Grok's non-end-turn Stop,
re-entrancy, the turn budget, the per-turn loop guard, an exhausted /goal,
then the message itself. TypeSafe judges the message (a deferred handoff,
an unproven claim). When TypeSafe can't answer (no response, a non-200, garbage),
the stop is allowed: a guess is worse than no judge. Either way the judgment is logged to
completion-gate-judgments.jsonl. Any block goes through
completion_gate_escalation, which caps how often one session can be blocked.

Fails OPEN on any parse error, missing file, or unexpected input: a false
block is far more costly than a missed one. When unsure, allow.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))

from completion_gate_escalation import (
    escalate_block,
    stop_rearming_goal,
)
from completion_gate_evidence import (
    EvidenceClaim,
    evaluate_evidence_block,
    extract_evidence_block,
)
from completion_gate_session_state import (
    GOAL_HANDOFF_PATH_ENV,
    GoalLedger,
    LoopGuard,
    RejectLedger,
    extract_goal_condition,
    goal_denial_count,
    reject_cap,
    turn_budget,
    turn_number_at_or_over_budget,
)
from completion_gate_transcript import TranscriptFacts, read_transcript_facts
from completion_gate_turn_evidence import build_digest, build_envelope
from completion_gate_turn_judge import (
    PATH_TYPESAFE,
    PATH_UNAVAILABLE,
    JudgmentLog,
    TurnJudge,
    TurnJudgment,
    block_reason,
    closing_line,
    request_state,
)
from hook_common import (
    Clock,
    Decision,
    HookEvent,
    HookSettings,
    run_hook,
    sha256_digest,
)

HOOK_NAME = "completion-gate"
END_TURN_REASON = "end_turn"
# A Stop that follows a hook block is judged, but the payload carries no turn_number for the
# loop guard, so the reject ledger alone bounds the chain. Teach this many times, then honor.
CHAIN_REJECT_CAP = 9
TYPESAFE_ALLOW_DETAIL = "typesafe-allow"
TYPESAFE_UNAVAILABLE_DETAIL = "typesafe-unavailable-allow:{reason}"
TRUNCATED_DETAIL_CHARS = 300


@dataclass(frozen=True, slots=True)
class StopTurn:
    """The Stop payload fields every check reads, plus this session's state."""

    session_id: str
    message: str
    transcript_path: str
    turn_number: str
    settings: HookSettings
    cap: int

    @classmethod
    def from_event(cls, event: HookEvent) -> StopTurn:
        return cls(
            session_id=event.session_id,
            message=event.field("last_assistant_message", "lastAssistantMessage"),
            transcript_path=event.field("transcript_path", "transcriptPath"),
            turn_number=event.field("turn_number", "turnNumber"),
            settings=HookSettings.from_env(),
            cap=min(reject_cap(), CHAIN_REJECT_CAP)
            if _stop_hook_active(event)
            else reject_cap(),
        )

    def loop_guard(self) -> LoopGuard | None:
        if not (self.session_id and self.turn_number):
            return None
        return LoopGuard(self.settings.state_dir / f"stop-loop-{self.session_id}.txt")

    def reject_ledger(self) -> RejectLedger | None:
        if not self.session_id:
            return None
        return RejectLedger(
            self.settings.state_dir / f"stop-reject-{self.session_id}.tsv"
        )


def _stop_hook_active(event: HookEvent) -> bool:
    """``.stop_hook_active // .stopHookActive`` is literally true."""
    value = event.payload.get("stop_hook_active")
    if value is None or value is False:
        value = event.payload.get("stopHookActive")
    return value is True


def _early_exit(event: HookEvent) -> Decision | None:
    reason = event.field("reason", "reason")
    if reason and reason != END_TURN_REASON:
        return Decision.no_objection(f"non-end-turn-reason-{reason}")
    if not event.field("last_assistant_message", "lastAssistantMessage"):
        return Decision.no_objection("no-last-assistant-message")
    if _stop_hook_active(event) and not event.session_id:
        return Decision.no_objection("stop-hook-already-active")
    return None


def _turn_budget_reached(turn: StopTurn) -> Decision | None:
    budget = turn_budget()
    if not turn_number_at_or_over_budget(turn.turn_number, budget):
        return None
    return Decision.no_objection(f"turn-budget-reached-{turn.turn_number}")


def _goal_exhausted(turn: StopTurn) -> Decision | None:
    condition = extract_goal_condition(turn.transcript_path)
    if not (condition and turn.session_id):
        return None
    ledger = GoalLedger(
        turn.settings.state_dir, turn.session_id, _goal_handoff_override()
    )
    if ledger.is_exhausted(sha256_digest(condition)):
        return stop_rearming_goal(
            ledger, "goal-condition-exhausted", condition, turn.cap
        )
    denials = goal_denial_count(turn.transcript_path, condition)
    if denials >= turn.cap:
        return stop_rearming_goal(
            ledger, f"goal-deny-cap-reached-{denials}", condition, turn.cap
        )
    return None


def _goal_handoff_override() -> str:
    return os.environ.get(GOAL_HANDOFF_PATH_ENV, "")


def _block(
    turn: StopTurn, reason: str, loop_guard: LoopGuard | None, since_iso: str
) -> Decision:
    return escalate_block(
        reason,
        turn.turn_number,
        loop_guard,
        turn.reject_ledger(),
        turn.cap,
        Clock.from_env(),
        since_iso,
    )


def _latest_prompt_at(facts: TranscriptFacts | None) -> str:
    """When the user last spoke: the start of the loop the reject cap bounds."""
    return facts.prompts[-1].at if facts is not None and facts.prompts else ""


def _judge_message(turn: StopTurn, loop_guard: LoopGuard | None) -> Decision:
    """TypeSafe's judgment of the message; an allow when TypeSafe can't answer."""
    evidence_text = extract_evidence_block(turn.message)
    claim = evaluate_evidence_block(
        evidence_text, turn.settings.state_dir, turn.session_id
    )
    facts = (
        read_transcript_facts(turn.transcript_path) if turn.transcript_path else None
    )
    digest = build_digest(facts, claim)
    envelope = build_envelope(turn.message, facts, digest)

    judgment = TurnJudge.from_env().judge(envelope)
    if judgment.decided:
        decision = _typesafe_decision(turn, judgment, claim, loop_guard, facts)
    else:
        decision = Decision.no_objection(
            TYPESAFE_UNAVAILABLE_DETAIL.format(reason=judgment.fallback_reason)
        )
    _record_judgment(turn, judgment, decision, envelope)
    return decision


def _typesafe_decision(
    turn: StopTurn,
    judgment: TurnJudgment,
    claim: EvidenceClaim,
    loop_guard: LoopGuard | None,
    facts: TranscriptFacts | None,
) -> Decision:
    if not judgment.blocks:
        return Decision.no_objection(TYPESAFE_ALLOW_DETAIL)
    reason = block_reason(judgment, turn.message, claim.missing)
    return _block(turn, reason, loop_guard, _latest_prompt_at(facts))


def _record_judgment(
    turn: StopTurn, judgment: TurnJudgment, decision: Decision, envelope: dict
) -> None:
    verdict = judgment.verdict
    JudgmentLog.in_state_dir(turn.settings.state_dir).record(
        {
            "ts": Clock.from_env().now_iso(),
            "session_id": turn.session_id,
            "turn_number": turn.turn_number,
            "path": PATH_TYPESAFE if judgment.decided else PATH_UNAVAILABLE,
            "fallback_reason": judgment.fallback_reason,
            "duration_ms": judgment.duration_ms,
            "state": request_state(envelope),
            "action": verdict.get("action"),
            "block_kind": verdict.get("block_kind"),
            "signals": verdict.get("signals"),
            "answers": verdict.get("answers"),
            "decision": decision.kind.value,
            "detail": (decision.log_detail or decision.message)[
                :TRUNCATED_DETAIL_CHARS
            ],
            "closing_line": closing_line(turn.message),
            "request": envelope,
            "response": verdict,
        }
    )


def decide(event: HookEvent) -> Decision | None:
    early = _early_exit(event)
    if early is not None:
        return early

    turn = StopTurn.from_event(event)
    budget_reached = _turn_budget_reached(turn)
    if budget_reached is not None:
        return budget_reached

    loop_guard = turn.loop_guard()
    if loop_guard is not None and loop_guard.already_blocked_twice_this_turn(
        turn.turn_number
    ):
        return Decision.no_objection(f"loop-guard-turn-{turn.turn_number}")

    return _goal_exhausted(turn) or _judge_message(turn, loop_guard)


if __name__ == "__main__":
    run_hook(HOOK_NAME, decide)
