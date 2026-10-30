"""Decodes an omp (oh-my-pi) session JSONL into transcript events.

omp's Stop hook names the session log as its transcript. Every row is
``{"type": ..., ...}``; only ``"message"`` rows carry the conversation, in a
``message`` envelope of role ``user``, ``assistant`` or ``toolResult``. The
other rows (hidden injected context, model usage, mode changes) are not turns.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

from completion_gate_claude_transcript import NON_PROMPT_PREFIXES
from completion_gate_transcript_events import (
    Prompt,
    Reply,
    ToolCall,
    ToolResult,
    TranscriptEvent,
    command_of,
)
from hook_common.event import RUN_COMMAND_TOOL, TOOL_NAME_ALIASES

SESSION_ROW = "session"
MESSAGE_ROW = "message"
USER_ATTRIBUTION = "user"
# The attributions that count as a prompt. omp marks a message a human typed as "user" and
# everything the harness delivers as "agent" — including the work order a parent agent
# delegated and that parent's later redirects. The harness's own injected context is not a
# message row at all (`custom_message`), so a consumer that wants the delegated task passes
# both; the completion gate keeps the default, where a subagent's turn has no ask of its own.
PROMPT_ATTRIBUTIONS = frozenset({USER_ATTRIBUTION})
TOOL_CALL_BLOCK = "toolCall"
TEXT_BLOCK = "text"
SHELL_TOOL_NAMES = frozenset({"bash"})
# omp mounts MCP capabilities behind a ``write`` to ``xd://<tool>`` whose content is the tool's JSON args.
DEVICE_TOOL = "write"
DEVICE_PREFIX = "xd://"
# omp rewrites a ``title`` row ahead of the ``session`` header, so the header is not always line 1.
HEADER_SEARCH_LINES = 3
HEADER_LINE_BYTES = 4096
# Skips the log's many non-conversation rows without decoding them.
RELEVANT_LINE_MARKER = f'"type":"{MESSAGE_ROW}"'


def is_omp_session(path: Path) -> bool:
    """True when the head of ``path`` holds omp's ``session`` header row."""
    try:
        with path.open("rb") as handle:
            heads = (
                handle.readline(HEADER_LINE_BYTES) for _ in range(HEADER_SEARCH_LINES)
            )
            return any(_is_session_header(head) for head in heads)
    except OSError:
        return False


def _is_session_header(line: bytes) -> bool:
    try:
        row = json.loads(line)
    except ValueError:
        return False
    return isinstance(row, dict) and row.get("type") == SESSION_ROW


def omp_events(
    lines: Iterable[str], prompt_attributions: frozenset[str] = PROMPT_ATTRIBUTIONS
) -> Iterator[TranscriptEvent]:
    for line in lines:
        row = _decode(line)
        if row is None:
            continue
        message = row["message"]
        role, content = message.get("role"), message.get("content")
        if role == "user":
            yield from _prompt(row, message, content, prompt_attributions)
        elif role == "assistant":
            yield Reply(_text_of(content))
            yield from _tool_calls(content)
        elif role == "toolResult":
            yield ToolResult(
                str(message.get("toolCallId")),
                _text_of(content),
                message.get("isError") is True,
            )


def _decode(line: str) -> dict[str, Any] | None:
    if RELEVANT_LINE_MARKER not in line:
        return None
    try:
        row = json.loads(line)
    except ValueError:
        return None
    if not isinstance(row, dict) or row.get("type") != MESSAGE_ROW:
        return None
    return row if isinstance(row.get("message"), dict) else None


def _prompt(
    row: dict[str, Any],
    message: dict[str, Any],
    content: Any,
    prompt_attributions: frozenset[str],
) -> Iterator[Prompt]:
    attribution = message.get("attribution")
    if attribution is not None and attribution not in prompt_attributions:
        return
    text = content.strip() if isinstance(content, str) else _text_of(content)
    if text and not text.startswith(NON_PROMPT_PREFIXES):
        yield Prompt(text, str(row.get("timestamp") or ""))


def _text_of(content: Any) -> str:
    """The prose in a message's content, without tool calls or thinking."""
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return ""
    parts = (
        block.get("text")
        for block in content
        if isinstance(block, dict) and block.get("type") == TEXT_BLOCK
    )
    return "\n".join(part for part in parts if isinstance(part, str) and part).strip()


def _tool_calls(content: Any) -> Iterator[ToolCall]:
    for block in content if isinstance(content, list) else ():
        if isinstance(block, dict) and block.get("type") == TOOL_CALL_BLOCK:
            name = str(block.get("name") or "")
            arguments = block.get("arguments")
            if name == DEVICE_TOOL and isinstance(arguments, dict):
                device = _device_call(arguments)
                if device is not None:
                    name, arguments = device
            yield ToolCall(
                str(block.get("id")), _canonical_tool(name), command_of(arguments)
            )


def _device_call(arguments: dict[str, Any]) -> tuple[str, Any] | None:
    """The tool and args a ``write`` to ``xd://<tool>`` stands for, or ``None`` for a plain write."""
    path = arguments.get("path")
    if not isinstance(path, str) or not path.startswith(DEVICE_PREFIX):
        return None
    return path.removeprefix(DEVICE_PREFIX), _device_args(arguments.get("content"))


def _device_args(content: Any) -> Any:
    """The arguments a device ``write`` carried, whatever shape the row holds.

    omp usually writes the tool's JSON args as a string, but a turn may pass them
    already decoded (an object), and older turns pass ``null``. Decoding only the
    string case and letting the rest through unchanged is the difference between a
    decoded call and a ``TypeError`` that fails the whole Stop gate open: the gate
    reads every row of the log, so one object-shaped row silenced it for the rest
    of the session (2026-10-29, omp:01a169a2).
    """
    if isinstance(content, (dict, list)):
        return content
    if not isinstance(content, str) or not content.strip():
        return None
    try:
        return json.loads(content)
    except ValueError:
        return None


def _canonical_tool(name: str) -> str:
    """omp's tool spelling in the Claude Code names the gate's rules match on."""
    if name in SHELL_TOOL_NAMES or RUN_COMMAND_TOOL.match(name):
        return "Bash"
    return TOOL_NAME_ALIASES.get(name, name)
