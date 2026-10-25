"""The reject cap bounds one request's loop; it must not outlive the request."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

from completion_gate_escalation import escalate_block
from completion_gate_session_state import RejectLedger
from hook_common import Clock, DecisionKind

LAST_USER_MESSAGE = "2026-10-01T12:11:18.000Z"


def _ledger(tmp_path: Path, stamps: list[str]) -> RejectLedger:
    path = tmp_path / "stop-reject-s.tsv"
    path.write_text("".join(f"{stamp}\thash{i}\n" for i, stamp in enumerate(stamps)))
    return RejectLedger(path)


def test_rejections_before_the_users_latest_message_do_not_count(
    tmp_path: Path,
) -> None:
    """85d309e7: five rejections from the evening before disabled the gate the next morning."""
    ledger = _ledger(tmp_path, [f"2026-09-30T16:2{i}:03Z" for i in range(5)])
    assert ledger.count() == 5
    assert ledger.count(LAST_USER_MESSAGE) == 0


def test_the_gate_still_blocks_after_old_rejections(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path, [f"2026-09-30T16:2{i}:03Z" for i in range(5)])
    decision = escalate_block(
        "do the work", "7", None, ledger, 5, Clock.from_env(), LAST_USER_MESSAGE
    )
    assert decision.kind is DecisionKind.BLOCK


def test_one_requests_loop_still_hits_the_cap(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path, [f"2026-10-01T12:3{i}:03Z" for i in range(5)])
    decision = escalate_block(
        "do the work", "7", None, ledger, 5, Clock.from_env(), LAST_USER_MESSAGE
    )
    assert decision.kind is DecisionKind.NO_OBJECTION
    assert decision.to_json() is None
