#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""SessionStart (matchers: startup, resume, compact) — H2 (durable goals
across compaction). If a goals file exists for this project (slug derived
from cwd the same way ~/.claude/projects/ does: replace "/" and "." with
"-"), print it to stdout so it is folded into the new context (per docs,
plain stdout text on a SessionStart command hook is treated as context).
If none exists, say so: do not invent work, and do not re-dispatch agents
blind after a reboot — require a handoff.md or refuse (ZYS-744). The hook
also appends the live atask claim's context (atask context --hook) when one
is active in this cwd, so a resumed session keeps the real task and its next
action rather than a stale goals line.

Never blocks. Fails open (silent, no output) on any error (via run_hook).
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))

from hook_common import Decision, HookEvent, run_hook

HOOK_NAME = "goals-recall"
# hc_log's decision word for this hook (hook-common.sh parity).
EMITTED_LOG_LABEL = "emitted"
GOALS_DIR_OVERRIDE_ENV = "HC_GOALS_DIR_OVERRIDE"
DEFAULT_GOALS_DIR = Path.home() / ".claude" / "goals"
SLUG_CHARS = re.compile(r"[/.]")
GOALS_FOUND_HEADER = (
    "Durable goals file for this project ({path}) — treat as current unless the user says "
    "otherwise; update the file whenever goals are set, changed, or completed (it survives "
    "compaction).\n\n"
)
NO_GOALS_MESSAGE = (
    "No durable goals file for this project ({path}). Do not invent work. After a reboot or "
    "resume, do not re-dispatch agents blind — require a handoff.md or refuse."
)
# Seconds the atask claim probe may take before the hook gives up on it (fail-open).
ATASK_TIMEOUT_SECONDS = 5
ATASK_BLOCK_HEADER = "\n\nLive task state (atask):\n"


def _goals_dir(env: Mapping[str, str] = os.environ) -> Path:
    override = env.get(GOALS_DIR_OVERRIDE_ENV)
    return Path(override) if override else DEFAULT_GOALS_DIR


def _slug_for(cwd: str) -> str:
    return SLUG_CHARS.sub("-", cwd)


def _live_atask_block(cwd: str) -> str:
    """The live atask claim's context for this cwd, or "" when there is none.

    The claim (objective, acceptance checks, next action) is the session's real goal; the goals
    file may lag it. Surfacing the claim at SessionStart keeps a resumed session on the live task.
    """
    try:
        result = subprocess.run(
            ["atask", "context", "--hook"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=ATASK_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    output = (result.stdout or "").strip()
    if result.returncode != 0 or not output or "status: no_active_claim" in output:
        return ""
    return ATASK_BLOCK_HEADER + output


def decide(event: HookEvent) -> Decision | None:
    cwd = event.field("cwd", "cwd")
    if not cwd:
        return None
    slug = _slug_for(cwd)
    if not slug:
        return None

    live = _live_atask_block(cwd)
    goals_file = _goals_dir() / f"{slug}.md"
    if goals_file.is_file():
        try:
            body = goals_file.read_text(encoding="utf-8")
        except OSError:
            return None
        text = GOALS_FOUND_HEADER.format(path=goals_file) + body + live
        return Decision.context(
            text, event_name="SessionStart", log_label=EMITTED_LOG_LABEL
        )

    text = NO_GOALS_MESSAGE.format(path=goals_file) + live
    return Decision.context(
        text, event_name="SessionStart", log_label=EMITTED_LOG_LABEL
    )


if __name__ == "__main__":
    run_hook(HOOK_NAME, decide)
