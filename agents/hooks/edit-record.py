#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""PostToolUse (Edit|Write matcher) — substantive-edit counter.

Mirrors bash-signature-record.py's shape: append-only per-session
recording, never blocks. reviewer-nudge.sh reads this count at Stop.

Fails OPEN on any parse error: always exits 0 (via run_hook).
"""

from __future__ import annotations

import contextlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))

from hook_common import Decision, HookEvent, HookSettings, run_hook

HOOK_NAME = "edit-record"
# hc_log's decision word for a successful recording (hook-common.sh parity) —
# distinct from the lib's generic "allow" no_objection label.
RECORDED_LOG_LABEL = "recorded"


def _record_edit(session_id: str) -> None:
    settings = HookSettings.from_env()
    settings.state_dir.mkdir(parents=True, exist_ok=True)
    counter = settings.state_dir / f"edit-count-{session_id}.txt"
    with contextlib.suppress(OSError), counter.open("a", encoding="utf-8") as handle:
        handle.write(".")


def decide(event: HookEvent) -> Decision | None:
    session_id = event.session_id
    if not session_id:
        return None
    _record_edit(session_id)
    return Decision.no_objection(f"session={session_id}", log_label=RECORDED_LOG_LABEL)


if __name__ == "__main__":
    run_hook(HOOK_NAME, decide)
