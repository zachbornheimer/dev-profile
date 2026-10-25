#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""UserPromptSubmit — surface the session transcript path so a compaction never
orphans the agent from its own history. The omp bridge adds transcript_path to
UserPromptSubmit payloads; Claude Code payloads carry it natively. One line per
prompt: a compaction summary does not say where the full pre-compaction history
lives, and sessions have spent dozens of commands rediscovering it. Never
blocks. Fails open on any error (via run_hook).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))

from hook_common import Decision, HookEvent, run_hook

HOOK_NAME = "transcript-path-note"
EMITTED_LOG_LABEL = "emitted"
LINE = (
    "Full pre-compaction history: {path} — this session's complete raw JSONL; "
    "grep it instead of reconstructing anything lost to compaction."
)


def decide(event: HookEvent) -> Decision | None:
    path = event.field("transcript_path", "transcriptPath")
    if not path:
        return None
    return Decision.context(
        LINE.format(path=path),
        event_name="UserPromptSubmit",
        log_label=EMITTED_LOG_LABEL,
    )


if __name__ == "__main__":
    run_hook(HOOK_NAME, decide)
