#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""PreCompact (matchers: manual, auto) — H2 (durable goals across
compaction), staleness half. PreCompact command hooks cannot instruct the
model to write content (only command/mcp_tool types are supported here, not
prompt/agent), so this appends a compaction-timestamp marker to the goals
file's own header rather than regenerating its content. When atask reports a
live claim (`atask context --hook`), the marker also carries that objective
condensed to one line, so the resumed context names the goal that is actually
running instead of the file's last rewrite. goals-recall.py (SessionStart,
matcher=compact) then surfaces the file, including those marker lines, to the
resumed context.

Never blocks compaction. Fails open on any error (via run_hook). No-op if no
goals file exists yet for this project.
"""

from __future__ import annotations

import contextlib
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))

from hook_common import Clock, Decision, HookEvent, run_hook

HOOK_NAME = "goals-note-compaction"
# hc_log's decision word for a rewritten goals file (hook-common.sh parity).
MARKED_LOG_LABEL = "marked"
GOALS_FILE_DIR = Path.home() / ".claude" / "goals"
SLUG_CHARS = re.compile(r"[/.]")
COMPACTED_MARKER_LINE = re.compile(r"^<!-- (compacted|current atask): ")
ATASK_CONTEXT_TIMEOUT_SECONDS = 2
ATASK_CONTEXT_MAX_CHARS = 400


def _atask_context_line() -> str:
    """The live objective, condensed to one comment line. Empty when atask is absent, answers
    nothing, or no claim is active: the marker then stays a timestamp alone, as before. `--` is
    rewritten because it would close the HTML comment the line lives in."""
    try:
        result = subprocess.run(
            ["atask", "context", "--hook"],
            capture_output=True,
            text=True,
            timeout=ATASK_CONTEXT_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if result.returncode != 0:
        return ""
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if not any(line.startswith("task:") and line != "task: null" for line in lines):
        return ""
    condensed = re.sub(r"-{2,}", "-", " | ".join(lines))[:ATASK_CONTEXT_MAX_CHARS]
    return f"<!-- current atask: {condensed} -->"


def _slug_for(cwd: str) -> str:
    return SLUG_CHARS.sub("-", cwd)


def _rewrite_with_marker(goals_file: Path, marker: str) -> bool:
    with contextlib.suppress(OSError):
        existing = goals_file.read_text(encoding="utf-8")
        kept_lines = [
            line
            for line in existing.splitlines()
            if not COMPACTED_MARKER_LINE.match(line)
        ]
        goals_file.write_text("\n".join([marker, *kept_lines]) + "\n", encoding="utf-8")
        return True
    return False


def decide(event: HookEvent) -> Decision | None:
    cwd = event.field("cwd", "cwd")
    if not cwd:
        return None
    slug = _slug_for(cwd)
    if not slug:
        return None

    goals_file = GOALS_FILE_DIR / f"{slug}.md"
    if not goals_file.is_file():
        return Decision.no_objection(f"no-goals-file:{slug}")

    lines = [f"<!-- compacted: {Clock.from_env().now_iso()} -->"]
    atask_line = _atask_context_line()
    if atask_line:
        lines.append(atask_line)
    marker = "\n".join(lines)
    if not _rewrite_with_marker(goals_file, marker):
        return None
    return Decision.no_objection(str(goals_file), log_label=MARKED_LOG_LABEL)


if __name__ == "__main__":
    run_hook(HOOK_NAME, decide)
