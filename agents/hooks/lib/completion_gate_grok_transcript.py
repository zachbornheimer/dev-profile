"""Decodes Grok's ``updates.jsonl`` update stream into transcript events.

Grok's Stop hook names ``updates.jsonl`` as its transcript. Unlike the
``chat_history.jsonl`` beside it, the stream keeps every turn across a
compaction and stamps each record with a time.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from completion_gate_transcript_events import (
    Prompt,
    Reply,
    ToolCall,
    ToolResult,
    TranscriptEvent,
    command_of,
)
from hook_common.event import TOOL_NAME_ALIASES

UPDATE_STREAM_NAME = "updates.jsonl"
USER_MESSAGE = "user_message_chunk"
AGENT_MESSAGE = "agent_message_chunk"
TOOL_STARTED = "tool_call"
TOOL_FINISHED = "tool_call_update"
FINISHED_STATUSES = ("completed", "failed")
FAILED_STATUS = "failed"
ISO_UTC_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
# Skips the stream's many other updates (thoughts, hooks) without decoding them.
RELEVANT_LINE_MARKERS = tuple(
    f'"sessionUpdate":"{kind}"'
    for kind in (USER_MESSAGE, AGENT_MESSAGE, TOOL_STARTED, TOOL_FINISHED)
)


def is_grok_update_stream(path: Path) -> bool:
    return path.name == UPDATE_STREAM_NAME


def grok_events(lines: Iterable[str]) -> Iterator[TranscriptEvent]:
    for line in lines:
        record = _decode(line)
        if record is None:
            continue
        update = record["params"]["update"]
        kind = update["sessionUpdate"]
        if kind == USER_MESSAGE:
            text = _message_text(update)
            if text:
                yield Prompt(text, _iso_time(record.get("timestamp")))
        elif kind == AGENT_MESSAGE:
            yield Reply(_message_text(update))
        elif kind == TOOL_STARTED:
            yield _tool_call(update)
        elif kind == TOOL_FINISHED:
            result = _tool_result(update)
            if result is not None:
                yield result


def _decode(line: str) -> dict[str, Any] | None:
    if not any(marker in line for marker in RELEVANT_LINE_MARKERS):
        return None
    try:
        record = json.loads(line)
    except ValueError:
        return None
    params = record.get("params") if isinstance(record, dict) else None
    update = params.get("update") if isinstance(params, dict) else None
    if not isinstance(update, dict) or "sessionUpdate" not in update:
        return None
    return record


def _iso_time(epoch_seconds: Any) -> str:
    if isinstance(epoch_seconds, bool) or not isinstance(epoch_seconds, int | float):
        return ""
    return datetime.fromtimestamp(epoch_seconds, UTC).strftime(ISO_UTC_FORMAT)


def _message_text(update: dict[str, Any]) -> str:
    content = update.get("content")
    if not isinstance(content, dict):
        return ""
    return str(content.get("text") or "").strip()


def _tool_call(update: dict[str, Any]) -> ToolCall:
    name = str(update.get("title") or "")
    return ToolCall(
        str(update.get("toolCallId")),
        TOOL_NAME_ALIASES.get(name, name),
        command_of(update.get("rawInput")),
    )


def _tool_result(update: dict[str, Any]) -> ToolResult | None:
    status = update.get("status")
    if status not in FINISHED_STATUSES:
        return None
    raw_output = update.get("rawOutput")
    raw_output = raw_output if isinstance(raw_output, dict) else {}
    exit_code = raw_output.get("exit_code")
    failed = (
        status == FAILED_STATUS
        or (isinstance(exit_code, int) and not isinstance(exit_code, bool) and exit_code != 0)
    )
    return ToolResult(str(update.get("toolCallId")), _output_text(update, raw_output), failed)


def _output_text(update: dict[str, Any], raw_output: dict[str, Any]) -> str:
    prompt_output = raw_output.get("output_for_prompt")
    if isinstance(prompt_output, str):
        return prompt_output
    blocks = update.get("content")
    if not isinstance(blocks, list):
        return ""
    texts = (
        block["content"].get("text")
        for block in blocks
        if isinstance(block, dict) and isinstance(block.get("content"), dict)
    )
    return "\n".join(text for text in texts if isinstance(text, str))
