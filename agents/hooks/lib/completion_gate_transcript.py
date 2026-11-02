"""The facts a Stop judgment may rest on, read from an agent's session log.

Only what a tool actually returned counts as evidence: a tool call and its
result, paired by id. A test result line that appears in a Read, in printed
source code, or in the assistant's own prose is not a test run.

Claude JSONL transcripts, omp session logs and Grok ``updates.jsonl`` update
streams are read. Anything else, such as legacy plain-text fixtures, yields
``None``; callers keep their raw-text behavior for it. Only the log's tail is read, so a FAIL older than that no longer counts.
"""

from __future__ import annotations

import contextlib
import os
from collections import deque
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

from completion_gate_claude_transcript import claude_events
from completion_gate_grok_transcript import grok_events, is_grok_update_stream
from completion_gate_omp_transcript import (
    PROMPT_ATTRIBUTIONS,
    is_omp_session,
    omp_events,
)
from completion_gate_transcript_events import (
    Notification,
    Prompt,
    Reply,
    ToolCall,
    ToolResult,
    TranscriptEvent,
)
from omp_session_store import readable_transcript

# ~0.5 s to decode under load; older test results than this are stale anyway.
TRANSCRIPT_TAIL_BYTES = 8_000_000
SHELL_TOOL = "Bash"
SUBAGENT_TOOL = "Agent"
TASK_NOTIFICATION_COMMAND = "task-notification"
HISTORY_TURNS_KEPT = 6
PROMPTS_KEPT = 40
# An omp prompt row is a "message" row whose message carries a user role and an
# attribution; both marks appear as raw bytes, so a recent-window scan can find
# prompt-shaped rows without json-decoding them. A row that merely echoes the
# marks inside tool output can only make the window start too late, which the
# fold detects and the caller repairs by reading the whole tail instead.
PROMPT_CANDIDATE_MARKS = (b'"role":"user"', b'"attribution"')


@dataclass(frozen=True, slots=True)
class ToolRun:
    """One tool call and what it returned."""

    tool: str
    command: str
    output: str
    failed: bool


@dataclass(frozen=True, slots=True)
class HistoryTurn:
    """An earlier exchange: what the user asked and what the agent last said back."""

    prompt: str
    reply: str


@dataclass(frozen=True, slots=True)
class UserPrompt:
    """One real user message and when it was sent, so a later turn can cite it."""

    text: str
    at: str


@dataclass(frozen=True, slots=True)
class TranscriptFacts:
    """Every tool run in the session, and the last real user prompt."""

    user_prompt: str
    runs: tuple[ToolRun, ...]
    turn_start: int  # index into runs of the first run after user_prompt
    history: tuple[
        HistoryTurn, ...
    ] = ()  # the exchanges before user_prompt, oldest first
    prompts: tuple[UserPrompt, ...] = ()  # every real user message kept, oldest first

    @property
    def turn_runs(self) -> tuple[ToolRun, ...]:
        return self.runs[self.turn_start :]


def read_transcript_facts(
    path: str, prompt_attributions: frozenset[str] = PROMPT_ATTRIBUTIONS
) -> TranscriptFacts | None:
    """``None`` when ``path`` is unreadable or holds no decodable records.

    Reads only the last TRANSCRIPT_TAIL_BYTES: a Stop hook has seconds, and a
    long session's transcript runs to hundreds of MB. ``prompt_attributions``
    decides which user-role messages count as a prompt (see
    ``completion_gate_omp_transcript.PROMPT_ATTRIBUTIONS``). An omp session kept
    only in the session database is read from there (``omp_session_store``).
    """
    log = readable_transcript(path)
    if log is None:
        return None
    decode = _decoder_for(log, prompt_attributions)
    with contextlib.suppress(OSError), log.open("rb") as handle:
        size = handle.seek(0, os.SEEK_END)
        return _fold_suffix(
            handle, decode, max(0, size - TRANSCRIPT_TAIL_BYTES), whole_tail=True
        )
    return None


def read_recent_facts(
    path: str,
    prompt_attributions: frozenset[str],
    prompts_needed: int,
) -> TranscriptFacts | None:
    """The newest prompts and the complete current turn, from a suffix of the log.

    The scope guard judges every tool call against the recent asks, so it reads
    the whole tail only to throw away almost all of it. This read folds from the
    ``prompts_needed``-th-newest prompt-shaped row onward — before the newest
    prompt, so the current turn's runs stay complete — and every consumer of
    ``prompts`` and ``turn_runs`` sees exactly what ``read_transcript_facts``
    shows. ``history`` and runs older than the newest prompt may be cut;
    callers that need them keep the whole-tail read.

    ``prompts_needed`` counts only prompts whose text is non-empty — the
    kind consumers slice. When the tail holds fewer such prompts than asked —
    or rows echoing the marks make the scan start too late — the fold comes up
    short and the whole tail is folded instead, the identical result.
    """
    log = readable_transcript(path)
    if log is None:
        return None
    decode = _decoder_for(log, prompt_attributions)
    with contextlib.suppress(OSError), log.open("rb") as handle:
        size = handle.seek(0, os.SEEK_END)
        if size == 0:
            return None
        tail_start = max(0, size - TRANSCRIPT_TAIL_BYTES)
        window_start = _recent_window_start(handle, tail_start, prompts_needed)
        facts = _fold_suffix(handle, decode, window_start, whole_tail=False)
        if (
            facts is None
            or sum(1 for item in facts.prompts if item.text.strip()) < prompts_needed
        ) and window_start > tail_start:
            facts = _fold_suffix(handle, decode, tail_start, whole_tail=True)
        return facts
    return None


def _decoder_for(
    log: Path, prompt_attributions: frozenset[str] = PROMPT_ATTRIBUTIONS
) -> Callable[[Iterable[str]], Iterator[TranscriptEvent]]:
    """The decoder for ``log``'s format, named by its head: the tail read drops the header."""
    if is_grok_update_stream(log):
        return grok_events
    if is_omp_session(log):
        return lambda lines: omp_events(lines, prompt_attributions)
    return claude_events


def _recent_window_start(handle, tail_start: int, prompts_needed: int) -> int:
    """The byte offset of the ``prompts_needed``-th-newest prompt-shaped row.

    ``tail_start`` when the tail holds fewer candidates, so the caller folds
    exactly what a whole-tail read would. Only bytes are examined; the fold
    decides whether the window really holds the prompts.
    """
    if prompts_needed <= 0:
        return tail_start
    handle.seek(tail_start)
    lines = handle.read().split(b"\n")
    # A partial first line at tail_start is not one the whole-tail read folds.
    skip_first = 1 if tail_start and lines else 0
    candidates: deque[int] = deque(maxlen=prompts_needed)
    offset = tail_start
    for index, line in enumerate(lines):
        if index < skip_first:
            offset += len(line) + 1
            continue
        if all(mark in line for mark in PROMPT_CANDIDATE_MARKS):
            candidates.append(offset)
        offset += len(line) + 1
    return candidates[0] if len(candidates) == prompts_needed else tail_start


def _fold_suffix(
    handle,
    decode: Callable[[Iterable[str]], Iterator[TranscriptEvent]],
    start: int,
    whole_tail: bool,
) -> TranscriptFacts | None:
    """Fold ``start`` to EOF; a whole-tail read drops a partial first line."""
    handle.seek(start)
    lines = handle.read().decode("utf-8", errors="replace").splitlines()
    if lines and '"customType":"session_exit"' in lines[-1]:
        return None
    return _fold(decode(lines[1:] if whole_tail and start else lines))


def _fold(events: Iterable[TranscriptEvent]) -> TranscriptFacts | None:
    pending: dict[str, ToolCall] = {}
    runs: list[ToolRun] = []
    prompt, turn_start, saw_event = "", 0, False
    reply, history, prompts = "", [], []
    for event in events:
        saw_event = True
        match event:
            case Prompt(text, at):
                if prompt:
                    history.append(HistoryTurn(prompt, reply))
                prompt, turn_start, reply = text, len(runs), ""
                prompts.append(UserPrompt(text, at))
            case Reply(text):
                reply = text or reply
            case Notification(text):
                runs.append(
                    ToolRun(SUBAGENT_TOOL, TASK_NOTIFICATION_COMMAND, text, False)
                )
            case ToolCall(call_id):
                pending[call_id] = event
            case ToolResult(call_id, output, failed):
                call = pending.pop(call_id, None)
                if call is not None:
                    runs.append(ToolRun(call.tool, call.command, output, failed))
    if not saw_event:
        return None
    return TranscriptFacts(
        prompt,
        tuple(runs),
        turn_start,
        tuple(history[-HISTORY_TURNS_KEPT:]),
        tuple(prompts[-PROMPTS_KEPT:]),
    )
