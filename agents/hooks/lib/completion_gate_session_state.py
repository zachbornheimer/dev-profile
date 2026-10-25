"""Session-scoped state for completion-gate.py's two loop-protection layers
and its /goal re-arm guard.

Layer 1 (RejectLedger): a session-wide reject counter + text-hash dedup.
The stop_hook_active check in the hook only ever catches immediate
re-entrancy within the SAME thrash cycle; a session that keeps making the
same unproven claim across many separate turns sails straight past it.
This is the actual backstop: cap total rejections per session at
HC_STOP_REJECT_CAP, and never let the SAME rejection text fire twice —
escalate the wording once per repeat, then stop blocking once the cap or
the escalation budget is exhausted.

Layer 2 (LoopGuard): a narrower per-turn guard that stops re-blocking the
exact same turn_number a third time. A second line of defense underneath
the session-wide cap, since turn_number resets across the very rejections
Layer 1 is counting.

GoalLedger: Claude's /goal is a session-scoped Stop hook whose command
text is the condition; it re-injects "Stop hook feedback:\n[condition]:"
until satisfied. After REJECT_CAP identical denials in one session, stop
re-arming that condition (write handoff.md, mark exhausted) until /new.
"""

from __future__ import annotations

import contextlib
import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_REJECT_CAP = 9
DEFAULT_TURN_BUDGET = 80
REJECT_CAP_ENV = "HC_STOP_REJECT_CAP"
TURN_BUDGET_ENV = "HC_TURN_BUDGET"
GOAL_HANDOFF_PATH_ENV = "HC_GOAL_HANDOFF_PATH"

LOOP_GUARD_REPEAT_THRESHOLD = 2
ISO_SECONDS_CHARS = 19  # 2026-10-01T12:42:31

GOAL_CONDITION_PREFIX = "session-scoped Stop hook is now active with condition: "
ESCAPE_CHAR = "\\"
QUOTE_CHAR = '"'


def _int_env(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def reject_cap() -> int:
    return _int_env(REJECT_CAP_ENV, DEFAULT_REJECT_CAP)


def turn_budget() -> int:
    return _int_env(TURN_BUDGET_ENV, DEFAULT_TURN_BUDGET)


def turn_number_at_or_over_budget(turn_number: str, budget: int) -> bool:
    """False for missing/non-numeric turn_number, matching the shell's
    `case '' | *[!0-9]*)` fail-open skip."""
    return turn_number.isdigit() and int(turn_number) >= budget


@dataclass(frozen=True, slots=True)
class RejectLedger:
    """stop-reject-<session>.tsv: one ``<iso>\\t<reason-hash>`` line per rejection."""

    path: Path

    def _entries(self, since_iso: str) -> list[list[str]]:
        """Rejections recorded at or after ``since_iso`` (every one when it is empty).

        The cap bounds a loop on one user request, so a rejection from an
        earlier request must not count toward it; ISO timestamps compare by
        their first ``ISO_SECONDS_CHARS`` characters.
        """
        with contextlib.suppress(OSError):
            fields = [line.split("\t") for line in self.path.read_text().splitlines()]
            cutoff = since_iso[:ISO_SECONDS_CHARS]
            return [
                f for f in fields if not cutoff or f[0][:ISO_SECONDS_CHARS] >= cutoff
            ]
        return []

    def count(self, since_iso: str = "") -> int:
        return len(self._entries(since_iso))

    def hash_seen(self, reason_hash: str, since_iso: str = "") -> bool:
        return any(
            len(f) >= 2 and f[1] == reason_hash for f in self._entries(since_iso)
        )

    def record(self, now_iso: str, reason_hash: str) -> None:
        with contextlib.suppress(OSError):
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(f"{now_iso}\t{reason_hash}\n")


@dataclass(frozen=True, slots=True)
class LoopGuard:
    """stop-loop-<session>.txt: a single ``<turn_number>\\t<count>`` line."""

    path: Path

    def already_blocked_twice_this_turn(self, turn_number: str) -> bool:
        prev_turn, prev_count = self._read()
        return prev_turn == turn_number and prev_count >= LOOP_GUARD_REPEAT_THRESHOLD

    def record_block(self, turn_number: str) -> None:
        prev_turn, prev_count = self._read()
        count = prev_count + 1 if prev_turn == turn_number else 1
        with contextlib.suppress(OSError):
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(f"{turn_number}\t{count}\n")

    def _read(self) -> tuple[str, int]:
        if not self.path.is_file():
            return "", 0
        with contextlib.suppress(OSError):
            fields = self.path.read_text().split("\t")
            turn = fields[0] if fields else ""
            try:
                count = int(fields[1]) if len(fields) > 1 else 0
            except ValueError:
                count = 0
            return turn, count
        return "", 0


def extract_goal_condition(transcript_path: str) -> str:
    """The most recently activated /goal condition text, or "" if none."""
    if not transcript_path:
        return ""
    path = Path(transcript_path)
    if not path.is_file():
        return ""
    with contextlib.suppress(OSError):
        return _last_goal_condition(path.read_text())
    return ""


def _last_goal_condition(text: str) -> str:
    """The quoted condition after the last harness sentence; the quote may be backslash-escaped."""
    end = len(text)
    while (start := text.rfind(GOAL_CONDITION_PREFIX, 0, end)) != -1:
        rest = text[start + len(GOAL_CONDITION_PREFIX) :].removeprefix(ESCAPE_CHAR)
        if rest.startswith(QUOTE_CHAR) and QUOTE_CHAR in rest[1:]:
            return rest[1:].split(QUOTE_CHAR, 1)[0]
        end = start
    return ""


def goal_denial_count(transcript_path: str, condition: str) -> int:
    """How many times the transcript carries "[<condition>]:" (a denial re-injection)."""
    if not transcript_path or not condition:
        return 0
    path = Path(transcript_path)
    if not path.is_file():
        return 0
    needle = f"[{condition}]:"
    with contextlib.suppress(OSError):
        return path.read_text().count(needle)
    return 0


@dataclass(frozen=True, slots=True)
class GoalLedger:
    """Whether a /goal condition has already been exhausted (handed off), and
    marking one exhausted: goal-handoff-<session>.md + a per-condition marker."""

    state_dir: Path
    session_id: str
    handoff_override: str = ""

    def handoff_path(self) -> Path:
        if self.handoff_override:
            return Path(self.handoff_override)
        return self.state_dir / f"goal-handoff-{self.session_id}.md"

    def _exhausted_marker_path(self, condition_hash: str) -> Path:
        return self.state_dir / f"goal-exhausted-{self.session_id}-{condition_hash}.txt"

    def is_exhausted(self, condition_hash: str) -> bool:
        return (
            bool(condition_hash)
            and self._exhausted_marker_path(condition_hash).is_file()
        )

    def mark_exhausted(self, condition: str, condition_hash: str) -> None:
        if not condition_hash:
            return
        with contextlib.suppress(OSError):
            self.state_dir.mkdir(parents=True, exist_ok=True)
            self._exhausted_marker_path(condition_hash).write_text(condition + "\n")

    def write_handoff(self, condition: str, cap: int) -> None:
        with contextlib.suppress(OSError):
            self.state_dir.mkdir(parents=True, exist_ok=True)
            self.handoff_path().write_text(
                "# Goal handoff\n\n"
                f"Session: {self.session_id}\n\n"
                f"The same Stop-hook /goal condition was denied {cap} times this session.\n"
                "It will not be re-armed until /new.\n\n"
                f"Condition:\n\n{condition}\n\n"
                "Continue remaining work in a fresh session (/new). Do not re-arm this goal.\n"
            )
