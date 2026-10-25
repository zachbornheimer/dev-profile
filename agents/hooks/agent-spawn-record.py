#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""PostToolUse (Agent|Task matcher) — subagent-spawn recorder.

Records that a fresh-context subagent (reviewer or otherwise) was spawned
this session, so reviewer-nudge.sh can tell "review happened" from "review
never happened" without re-deriving it from the transcript.

Fails OPEN on any parse error or unexpected input: always no-decision.
"""

from __future__ import annotations

import contextlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))

from hook_common import Clock, Decision, HookEvent, HookSettings, run_hook

HOOK_NAME = "agent-spawn-record"
MARKER_NAME_PREFIX = "agent-spawn-"
ABSENT_SUBAGENT_TYPE = "<absent>"
RECORDED_LOG_LABEL = "recorded"


def _append_marker(state_dir: Path, session_id: str, subagent_type: str) -> None:
    with contextlib.suppress(OSError):
        state_dir.mkdir(parents=True, exist_ok=True)
        marker = state_dir / f"{MARKER_NAME_PREFIX}{session_id}.txt"
        with marker.open("a", encoding="utf-8") as handle:
            handle.write(f"{Clock.from_env().now_iso()}\t{subagent_type}\n")


def decide(event: HookEvent) -> Decision | None:
    if event.tool_name not in ("Agent", "Task"):
        return None

    session_id = event.session_id
    if not session_id:
        return None

    subagent_type = event.subagent_type or ABSENT_SUBAGENT_TYPE
    _append_marker(HookSettings.from_env().state_dir, session_id, subagent_type)
    return Decision.no_objection(
        f"session={session_id} subagent_type={subagent_type}", log_label=RECORDED_LOG_LABEL
    )


if __name__ == "__main__":
    run_hook(HOOK_NAME, decide)
