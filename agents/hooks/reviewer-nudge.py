#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Stop hook — reviewer nudge. Non-blocking companion to edit-record.sh and
agent-spawn-record.sh: if this session made a substantial number of edits
and never spawned a subagent (reviewer or otherwise), reminds the agent
that a fresh-context review is cheap insurance before calling work done.
Never blocks.

Dedup: emits at most once per distinct edit count. A repeated Stop with
no new edits since the last emission (the common case: consecutive turns
where nothing changed) stays silent — re-emitting an unchanged nudge
every Stop trains the model to ignore it. It re-fires only once the edit
count has grown past the count last emitted at.

Fails OPEN (silently, no output) on any parse error or missing state.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))

import contextlib

from hook_common import Decision, HookEvent, HookSettings, run_hook

HOOK_NAME = "reviewer-nudge"
SELF_DIR = Path(__file__).resolve().parent

# Threshold at which "no review yet" starts being worth mentioning. Below
# this, most turns are small enough that a reviewer spawn would be
# overhead, not insurance.
SUBSTANTIVE_EDIT_COUNT_THRESHOLD = 5
NUDGE_MESSAGE = (
    "Substantive edits this session with no fresh-context review — consider a reviewer agent "
    "before calling this done."
)
# Generous: the reap script's own internal budgets (ps timeout + ancestor
# walk) can sum past a few seconds; this call must never be the reason a
# Stop hook feels slow, but it also must not get silently truncated before
# it ever reaches its own hc_log call (shell's original wrapper has no
# timeout at all).
SSH_REAP_TIMEOUT_SECS = 20


def _reap_leftover_ssh(event: HookEvent) -> None:
    """ZYS-732: session-scoped leftover-ssh cleanup, piggybacked on this Stop.

    Best-effort and fire-and-forget, exactly like the former shell wrapper's
    `... | ssh-session-reap.sh >/dev/null 2>&1 || true`.
    """
    with contextlib.suppress(OSError, subprocess.SubprocessError):
        subprocess.run(
            [str(SELF_DIR / "ssh-session-reap.py")],
            input=json.dumps(event.payload),
            text=True,
            capture_output=True,
            timeout=SSH_REAP_TIMEOUT_SECS,
            check=False,
        )


def _edit_count(state_dir: Path, session_id: str) -> int | None:
    edit_counter = state_dir / f"edit-count-{session_id}.txt"
    if not edit_counter.is_file():
        return None
    try:
        return edit_counter.stat().st_size
    except OSError:
        return None


def _has_recorded_review(state_dir: Path, session_id: str) -> bool:
    spawn_marker = state_dir / f"agent-spawn-{session_id}.txt"
    return spawn_marker.is_file() and spawn_marker.stat().st_size > 0


def _last_nudged_at(state_dir: Path, session_id: str) -> int:
    sent_marker = state_dir / f"reviewer-nudge-sent-{session_id}.txt"
    try:
        return int(sent_marker.read_text().strip())
    except (OSError, ValueError):
        return 0


def decide(event: HookEvent) -> Decision | None:
    reason = event.field("reason", "reason")
    if reason and reason != "end_turn":
        return None

    session_id = event.session_id
    if not session_id:
        return None

    _reap_leftover_ssh(event)

    state_dir = HookSettings.from_env().state_dir
    edit_count = _edit_count(state_dir, session_id)
    if edit_count is None or edit_count < SUBSTANTIVE_EDIT_COUNT_THRESHOLD:
        return None

    if _has_recorded_review(state_dir, session_id):
        return Decision.no_objection(f"edits={edit_count} review-recorded")

    last_nudged_at = _last_nudged_at(state_dir, session_id)
    if edit_count <= last_nudged_at:
        return Decision.no_objection(
            f"edits={edit_count} already-nudged-at={last_nudged_at}"
        )

    sent_marker = state_dir / f"reviewer-nudge-sent-{session_id}.txt"
    with contextlib.suppress(OSError):
        sent_marker.write_text(str(edit_count))
    return Decision.context(
        NUDGE_MESSAGE,
        "Stop",
        "nudged",
        log_detail=f"edits={edit_count} no-review-recorded",
    )


if __name__ == "__main__":
    run_hook(HOOK_NAME, decide)
