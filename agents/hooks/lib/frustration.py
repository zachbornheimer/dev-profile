"""Deterministic frustration scoring for one user prompt. No model call.

A learner agent is launched when the score reaches ``THRESHOLD``. Every signal is
a cheap lexical or transcript fact, so the hook adds no latency to a prompt and
its verdict is reproducible from the same inputs.

Prompts longer than ``MAX_PROMPT_CHARS`` score zero: a human reacting to an agent
writes a short message, while long prompts are pasted logs, injected skill bodies,
or dictated specs whose capitals and "again" mean nothing about mood.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

MAX_PROMPT_CHARS = 500
THRESHOLD = 3
ERROR_WINDOW = 10
ERROR_STREAK = 4
REPEAT_SIMILARITY = 0.6
REPEAT_MIN_WORDS = 6
CAPS_MIN_LETTERS = 15
CAPS_RATIO = 0.6
TAIL_BYTES = 512 * 1024
PRIOR_PROMPTS = 3

PROFANITY = re.compile(
    r"\b(wtf|wth|ffs|jfc|fuck\w*|shit\w*|damn(it)?|goddamn\w*|bullshit|crap)\b",
    re.IGNORECASE,
)
# The user says they already said it, or asks why the agent did not do what was expected: a
# correction of the agent, enough alone to launch a learner.
REPRIMAND = re.compile(
    r"i (already |just )?told you|how many times|didn'?t i (just )?(say|tell|ask)"
    r"|not what i (asked|said|wanted|meant)"
    r"|why (aren'?t|are you not|didn'?t|wouldn'?t) you|what'?s causing you to",
    re.IGNORECASE,
)
STRONG = re.compile(
    r"for the love of|i (just )?said\b|you (keep|still|never|ignored|ignore)\b"
    r"|this is (ridiculous|unacceptable|absurd)|(so|really|completely) useless"
    r"|stop (doing|ignoring|it\b)|why (are|did|do) you (still|keep|always)",
    re.IGNORECASE,
)
MILD = re.compile(
    r"\b(again|still (not|doesn'?t|isn'?t|broken|wrong)|wrong|nope|that'?s not|frustrat\w*"
    r"|annoy\w*|come on|seriously)\b|^no[,.!]",
    re.IGNORECASE,
)
STACKED_PUNCTUATION = re.compile(r"[!?]{2,}")
WORD = re.compile(r"[a-z0-9']{3,}")
# Text a harness injects into the user role: task notifications, reminders, interrupt markers.
# Not something the human typed, so it neither scores nor counts as an earlier prompt.
MACHINE_TEXT = re.compile(r"\s*(<[a-z][\w-]*[\s>]|\[Request interrupted|\[Image|Caveat:)", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class Score:
    total: int
    reasons: tuple[str, ...]

    @property
    def triggered(self) -> bool:
        return self.total >= THRESHOLD


def _words(text: str) -> frozenset[str]:
    return frozenset(WORD.findall(text.lower()))


def _similar(a: str, b: str) -> bool:
    left, right = _words(a), _words(b)
    if len(left) < REPEAT_MIN_WORDS or len(right) < REPEAT_MIN_WORDS:
        return False
    return len(left & right) / len(left | right) >= REPEAT_SIMILARITY


def _shouting(text: str) -> bool:
    letters = [c for c in text if c.isalpha()]
    if len(letters) < CAPS_MIN_LETTERS:
        return False
    return sum(c.isupper() for c in letters) / len(letters) >= CAPS_RATIO


def score(prompt: str, prior_prompts: Iterable[str] = (), recent_tool_errors: int = 0) -> Score:
    """Score ``prompt`` against the user's earlier prompts and the recent tool-error count."""
    text = prompt.strip()
    if not text or len(text) > MAX_PROMPT_CHARS or MACHINE_TEXT.match(text):
        return Score(0, ())

    total = 0
    reasons: list[str] = []

    def add(points: int, reason: str) -> None:
        nonlocal total
        total += points
        reasons.append(reason)

    if PROFANITY.search(text):
        add(3, "profanity")
    if REPRIMAND.search(text):
        add(3, "reprimand")
    elif STRONG.search(text):
        add(2, "blame-phrase")
    mild = {m.group(0).lower() for m in MILD.finditer(text)}
    if mild:
        add(min(len(mild), 2), "mild-phrase")
    if _shouting(text):
        add(2, "caps")
    if STACKED_PUNCTUATION.search(text):
        add(1, "stacked-punctuation")
    if any(_similar(text, earlier) for earlier in prior_prompts):
        add(1, "repeated-request")
    if recent_tool_errors >= ERROR_STREAK:
        add(1, f"tool-errors={recent_tool_errors}")
    return Score(total, tuple(reasons))


def _text_of(content: object) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    return "\n".join(
        part["text"]
        for part in content
        if isinstance(part, dict) and part.get("type") == "text" and isinstance(part.get("text"), str)
    )


def _tail_entries(path: Path) -> list[dict]:
    """Parsed JSONL entries from the end of ``path``; the first line is dropped when cut mid-line."""
    try:
        size = path.stat().st_size
        with path.open("rb") as handle:
            handle.seek(max(0, size - TAIL_BYTES))
            raw = handle.read().decode("utf-8", errors="replace")
    except OSError:
        return []
    lines = raw.splitlines()
    if size > TAIL_BYTES and lines:
        lines = lines[1:]
    entries = []
    for line in lines:
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if isinstance(entry, dict):
            entries.append(entry)
    return entries


def _classify(entry: dict) -> tuple[str, str, bool]:
    """(kind, text, is_error) with kind ``user`` | ``tool_result`` | ``other``.

    Handles the omp shape (``type: message``, ``message.role``) and the Claude
    shape (``type: user``, tool results as ``tool_result`` content parts).
    """
    message = entry.get("message")
    if not isinstance(message, dict):
        return "other", "", False
    role = message.get("role")
    if role == "toolResult":
        return "tool_result", "", message.get("isError") is True
    if role != "user":
        return "other", "", False
    content = message.get("content")
    if isinstance(content, list):
        parts = [p for p in content if isinstance(p, dict)]
        results = [p for p in parts if p.get("type") == "tool_result"]
        if results:
            return "tool_result", "", any(p.get("is_error") is True for p in results)
    if entry.get("isMeta") is True or entry.get("isSidechain") is True:
        return "other", "", False
    text = _text_of(content)
    return ("other", "", False) if MACHINE_TEXT.match(text) else ("user", text, False)


def transcript_signals(
    path: Path | None, current_prompt: str
) -> tuple[list[str], int]:
    """(earlier user prompts, tool errors among the last ``ERROR_WINDOW`` tool results).

    The prompt being scored may already be on disk when the hook runs; the newest
    earlier prompt is dropped when it is the same text so it never matches itself.
    """
    if path is None:
        return [], 0
    classified = [_classify(entry) for entry in _tail_entries(path)]
    prompts = [text.strip() for kind, text, _ in classified if kind == "user" and text.strip()]
    if prompts and prompts[-1] == current_prompt.strip():
        prompts.pop()
    results = [is_error for kind, _, is_error in classified if kind == "tool_result"]
    return prompts[-PRIOR_PROMPTS:], sum(results[-ERROR_WINDOW:])
