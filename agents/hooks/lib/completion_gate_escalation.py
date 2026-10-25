"""What completion-gate emits once it has a reason to block a Stop.

A block is never unconditional: the loop guard records it, the reject
ledger caps how many times one user request can be blocked, an identical
reason is restated (never silently repeated), and a /goal condition that
keeps getting denied stops re-arming. Each of those ends in a silent
allow (Decision.no_objection): Grok treats Stop additionalContext as
continue, the same as a decision block, so the portable end-the-turn
path is empty stdout plus a log line.
"""

from __future__ import annotations

from completion_gate_session_state import GoalLedger, LoopGuard, RejectLedger
from hook_common import Clock, Decision, sha256_digest

REJECT_CAP_REACHED_DETAIL = "reject-cap-reached-{count}"
ESCALATION_EXHAUSTED_DETAIL = "reject-escalation-exhausted"
REPEATED_REJECTION_PREFIX = "[repeated rejection, attempt {attempt}] "


def stop_rearming_goal(
    ledger: GoalLedger, log_detail: str, condition: str, cap: int
) -> Decision:
    ledger.write_handoff(condition, cap)
    ledger.mark_exhausted(condition, sha256_digest(condition))
    return Decision.no_objection(log_detail)


def _cap_reached(count: int) -> Decision:
    return Decision.no_objection(REJECT_CAP_REACHED_DETAIL.format(count=count))


def _escalation_exhausted() -> Decision:
    return Decision.no_objection(ESCALATION_EXHAUSTED_DETAIL)


def _last_rejection_warning(reason: str, count: int, cap: int) -> str:
    return (
        f"{reason}\n\nThis is rejection {count} of {cap} for this request. If "
        "the bar above is still unmet after this, the next Stop will end the loop "
        "instead of blocking again, so finish the work now or state plainly what is "
        "still open and why."
    )


def _capped_block(
    reason: str, ledger: RejectLedger, cap: int, clock: Clock, since_iso: str
) -> Decision:
    count = ledger.count(since_iso)
    if count >= cap:
        return _cap_reached(count)

    restated = reason
    attempt = 1
    while ledger.hash_seen(sha256_digest(restated), since_iso):
        attempt += 1
        if attempt > cap:
            return _escalation_exhausted()
        restated = REPEATED_REJECTION_PREFIX.format(attempt=attempt) + reason

    ledger.record(clock.now_iso(), sha256_digest(restated))
    count += 1
    if count >= cap:
        restated = _last_rejection_warning(restated, count, cap)
    return Decision.block(restated)


def escalate_block(
    reason: str,
    turn_number: str,
    loop_guard: LoopGuard | None,
    reject_ledger: RejectLedger | None,
    cap: int,
    clock: Clock,
    since_iso: str = "",
) -> Decision:
    """Block the Stop with ``reason``, unless the reject cap says stop instead.

    The cap counts rejections since ``since_iso`` (the user's latest message), so
    one request's loop can't exhaust the gate for the rest of a long session.
    """
    if loop_guard is not None:
        loop_guard.record_block(turn_number)
    if reject_ledger is None:
        return Decision.block(reason)
    return _capped_block(reason, reject_ledger, cap, clock, since_iso)
