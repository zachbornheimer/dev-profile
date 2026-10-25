"""Decodes a Claude Code JSONL transcript into transcript events."""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from typing import Any

from completion_gate_transcript_events import (
    Notification,
    Prompt,
    Reply,
    ToolCall,
    ToolResult,
    TranscriptEvent,
    command_of,
)

TASK_NOTIFICATION_PREFIX = "<task-notification"
# Lines worth decoding: tool calls, tool results, and user prompts.
RELEVANT_LINE_MARKERS = (
    '"tool_use"',
    '"tool_result"',
    '"type":"user"',
    '"type":"assistant"',
)
NON_PROMPT_PREFIXES = (
    "<command-",
    "<local-command",
    "<system-reminder",
    "<task-notification",
    "<bash-",
    "Stop hook feedback:",
    "[Request interrupted by user",
)


def claude_events(lines: Iterable[str]) -> Iterator[TranscriptEvent]:
    for line in lines:
        record = _decode(line)
        if record is None:
            continue
        content = (record.get("message") or {}).get("content")
        if record.get("type") == "user":
            yield from _user_events(record, content)
        elif record.get("type") == "assistant":
            yield Reply(_assistant_text(content))
        for block in content if isinstance(content, list) else ():
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use":
                yield ToolCall(
                    str(block.get("id")),
                    str(block.get("name") or ""),
                    command_of(block.get("input")),
                )
            elif block.get("type") == "tool_result":
                yield ToolResult(
                    str(block.get("tool_use_id")),
                    _result_text(block),
                    block.get("is_error") is True,
                )


def _user_events(record: dict[str, Any], content: Any) -> Iterator[TranscriptEvent]:
    text = _user_text(record, content)
    if text.startswith(TASK_NOTIFICATION_PREFIX):
        yield Notification(text)
    elif text and not text.startswith(NON_PROMPT_PREFIXES):
        yield Prompt(text, str(record.get("timestamp") or ""))


def _decode(line: str) -> dict[str, Any] | None:
    if not any(marker in line for marker in RELEVANT_LINE_MARKERS):
        return None
    try:
        record = json.loads(line)
    except ValueError:
        return None
    return record if isinstance(record, dict) else None


def _user_text(record: dict[str, Any], content: Any) -> str:
    """The text a user record carries — a prompt, a notification, or hook feedback — or ""."""
    if record.get("isMeta") or record.get("isCompactSummary"):
        return ""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list) and all(
        isinstance(b, dict) and b.get("type") == "text" for b in content
    ):
        return "\n".join(str(b.get("text") or "") for b in content).strip()
    return ""


def _assistant_text(content: Any) -> str:
    """The prose an assistant record carries, without tool calls or thinking."""
    if not isinstance(content, list):
        return ""
    parts = (
        b.get("text")
        for b in content
        if isinstance(b, dict) and b.get("type") == "text"
    )
    return "\n".join(str(part) for part in parts if part).strip()


def _result_text(block: dict[str, Any]) -> str:
    content = block.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            str(part.get("text") or "") for part in content if isinstance(part, dict)
        )
    return ""
