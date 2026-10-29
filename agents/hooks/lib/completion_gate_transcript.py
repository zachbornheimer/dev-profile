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
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

from completion_gate_claude_transcript import claude_events
from completion_gate_grok_transcript import grok_events, is_grok_update_stream
from completion_gate_omp_transcript import is_omp_session, omp_events
from completion_gate_transcript_events import (
    Notification,
    Prompt,
    Reply,
    ToolCall,
    ToolResult,
    TranscriptEvent,
)

# ~0.5 s to decode under load; older test results than this are stale anyway.
TRANSCRIPT_TAIL_BYTES = 8_000_000
SHELL_TOOL = "Bash"
SUBAGENT_TOOL = "Agent"
TASK_NOTIFICATION_COMMAND = "task-notification"
HISTORY_TURNS_KEPT = 6
PROMPTS_KEPT = 40


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


def read_transcript_facts(path: str) -> TranscriptFacts | None:
    """``None`` when ``path`` is unreadable or holds no decodable records.

    Reads only the last TRANSCRIPT_TAIL_BYTES: a Stop hook has seconds, and a
    long session's transcript runs to hundreds of MB.
    """
    log = Path(path)
    decode = _decoder_for(log)
    with contextlib.suppress(OSError), log.open("rb") as handle:
        size = handle.seek(0, os.SEEK_END)
        start = max(0, size - TRANSCRIPT_TAIL_BYTES)
        handle.seek(start)
        lines = handle.read().decode("utf-8", errors="replace").splitlines()
        return _fold(decode(lines[1:] if start else lines))
    return None


def _decoder_for(log: Path) -> Callable[[Iterable[str]], Iterator[TranscriptEvent]]:
    """The decoder for ``log``'s format, named by its head: the tail read drops the header."""
    if is_grok_update_stream(log):
        return grok_events
    return omp_events if is_omp_session(log) else claude_events


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
