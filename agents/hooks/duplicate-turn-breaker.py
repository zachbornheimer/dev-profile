#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Stop hook — break a turn whose final message repeats the previous one verbatim.

Incident (claude:2ed0c871, 2026-10-19): a readability gate asked for rewrites and
the agent re-rendered the same message three times per attempt. The clarity-gate's
reject cap bounds that in-hook loop, but nothing watched the cross-turn case: a
terse user reply answered with the same wall of text again.

This hook compares the current final message with the immediately preceding
exchange's reply. It blocks ONCE per session when ALL of these hold:

- the two messages are substantially identical (normalized word-set Jaccard
  >= HC_DUPLICATE_JACCARD, default 0.85), and
- both carry enough prose to be a report (>= HC_DUPLICATE_MIN_CHARS, default 160
  normalized characters — "ok" and one-line statuses never trip it), and
- the current turn ran no tool calls (repetition after new work can be a
  legitimate status update; repetition instead of work is the failure).

The block says what to do instead: act, or end with one line naming what
changed. A ledger file fires it at most once per session, so the breaker can
never become its own loop. Every parse error, missing transcript, or missing
field fails open — a missed duplicate costs less than a false block.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))

from completion_gate_session_state import RejectLedger
from completion_gate_transcript import read_transcript_facts
from hook_common import Clock, Decision, HookEvent, HookSettings, run_hook

HOOK_NAME = "duplicate-turn-breaker"
OFF_ENV = "HC_DUPLICATE_BREAKER_OFF"
THRESHOLD_ENV = "HC_DUPLICATE_JACCARD"
MIN_CHARS_ENV = "HC_DUPLICATE_MIN_CHARS"
DEFAULT_THRESHOLD = 0.85
DEFAULT_MIN_CHARS = 160
LEDGER_PREFIX = "duplicate-turn-"

MESSAGE_KEYS = (
    "last_assistant_message",
    "lastAssistantMessage",
    "final_response",
    "finalResponse",
    "assistant_response",
    "assistantResponse",
)

BLOCK_REASON = (
    "Your last two messages are substantially identical and this turn ran no tools. "
    "Do not send that report again. Either take the next concrete action now, or end "
    "with one short line naming what changed since the previous message, or the single "
    "blocker if nothing changed."
)

_NORMALIZE_RE = re.compile(r"[^a-z0-9]+")


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _message(event: HookEvent) -> str:
    extra = event.payload.get("extra")
    extra = extra if isinstance(extra, dict) else {}
    for key in MESSAGE_KEYS:
        text = _text(event.payload.get(key)) or _text(extra.get(key))
        if text:
            return text
    return ""


def _env_float(name: str, default: float) -> float:
    try:
        value = float(os.environ.get(name, ""))
    except ValueError:
        return default
    return value if value > 0 else default


def _env_int(name: str, default: int) -> int:
    try:
        value = int(os.environ.get(name, ""))
    except ValueError:
        return default
    return value if value >= 0 else default


def _words(text: str) -> frozenset[str]:
    return frozenset(_NORMALIZE_RE.sub(" ", text.lower()).split())


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _is_repeat(current: str, previous: str, threshold: float, min_chars: int) -> bool:
    if len(current) < min_chars or len(previous) < min_chars:
        return False
    return _jaccard(_words(current), _words(previous)) >= threshold


def decide(event: HookEvent) -> Decision | None:
    if os.environ.get(OFF_ENV):
        return Decision.no_objection("breaker off")
    transcript_path = event.field("transcript_path", "transcriptPath")
    current = _message(event)
    if not transcript_path or not current:
        return Decision.no_objection("no transcript or message")
    facts = read_transcript_facts(transcript_path)
    if facts is None or not facts.history:
        return Decision.no_objection("no previous exchange")
    previous = facts.history[-1].reply
    if not previous:
        return Decision.no_objection("previous reply empty")
    if facts.turn_runs:
        return Decision.no_objection("turn ran tools")

    threshold = _env_float(THRESHOLD_ENV, DEFAULT_THRESHOLD)
    min_chars = _env_int(MIN_CHARS_ENV, DEFAULT_MIN_CHARS)
    if not _is_repeat(current, previous, threshold, min_chars):
        return Decision.no_objection("messages differ")

    session = event.session_id or "unknown"
    ledger = RejectLedger(HookSettings.from_env().state_dir / f"{LEDGER_PREFIX}{session}.tsv")
    if ledger.count() > 0:
        return Decision.no_objection("already fired this session")
    ledger.record(Clock.from_env().now_iso(), "duplicate")
    return Decision.block(BLOCK_REASON)


if __name__ == "__main__":
    run_hook(HOOK_NAME, decide)
