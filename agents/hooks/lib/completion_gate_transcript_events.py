"""What a transcript says happened, in a shape no agent's log format owns."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

COMMAND_KEYS = ("command", "description", "file_path", "pattern")


@dataclass(frozen=True, slots=True)
class Prompt:
    """A real user message."""

    text: str
    at: str = ""


@dataclass(frozen=True, slots=True)
class Reply:
    """An assistant message; ``text`` is empty when it only called tools."""

    text: str


@dataclass(frozen=True, slots=True)
class ToolCall:
    call_id: str
    tool: str
    command: str


@dataclass(frozen=True, slots=True)
class ToolResult:
    call_id: str
    output: str
    failed: bool


@dataclass(frozen=True, slots=True)
class Notification:
    """A subagent's completion report delivered as a user record."""

    text: str


TranscriptEvent = Prompt | Reply | ToolCall | ToolResult | Notification


def command_of(tool_input: Any) -> str:
    """The first non-empty of command/description/file_path/pattern, or ""."""
    if not isinstance(tool_input, dict):
        return ""
    for key in COMMAND_KEYS:
        value = tool_input.get(key)
        if isinstance(value, str) and value:
            return value
    return ""
