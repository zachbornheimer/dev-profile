"""Source-preserving native parsers, bounded overlapping windows."""

import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from learnings.edges import Files
from learnings.models import Message

SYNTHETIC_PREFIXES = (
    "Stop hook feedback:",
    "Another Claude session sent a message:",
    "Goal check-in:",
    "Base directory for this skill:",
    "[Usage limit reached.",
    "[zach-factory]",
    "You are a bounded implementation worker",
    "<system-reminder>",
    "This session is being continued from a previous conversation",
)


class Block(BaseModel):
    model_config = ConfigDict(extra="allow")
    type: str
    text: str = ""
    content: str | list["Block"] = ""


class Turn(BaseModel):
    model_config = ConfigDict(extra="allow")
    role: str = ""
    content: str | list[Block] = ""


class Native(BaseModel):
    model_config = ConfigDict(extra="allow")
    type: str = ""
    role: str = ""
    uuid: str | None = None
    sessionId: str | None = None
    timestamp: str | None = None
    synthetic_reason: str | None = None
    isMeta: bool = False
    synthetic: bool = False
    message: Turn | None = None
    content: str | list[Block] = ""


def texts(content: str | list[Block]) -> list[tuple[str, str]]:
    if isinstance(content, str):
        return [("text", content)]
    result: list[tuple[str, str]] = []
    for block in content:
        if block.type == "tool_result":
            result.extend(("tool", text) for _, text in texts(block.content))
        elif block.type == "text":
            result.append(("text", block.text))
    return result


def native_messages(raw: str, path: Path) -> list[Message]:
    result: list[Message] = []
    for line, entry in enumerate(raw.splitlines(), 1):
        if not entry.strip():
            continue
        turn = Native.model_validate_json(entry)
        role = turn.message.role if turn.message else (turn.role or turn.type)
        if role not in {"user", "assistant", "tool", "system"}:
            continue
        content = turn.message.content if turn.message else turn.content
        for part, (kind, text) in enumerate(texts(content)):
            if not text:
                continue
            actual: Literal["user", "assistant", "tool", "system"] = "system"
            if kind == "tool" or role == "tool":
                actual = "tool"
            elif role == "user":
                actual = "user"
            elif role == "assistant":
                actual = "assistant"
            synthetic = turn.synthetic or turn.isMeta or bool(turn.synthetic_reason)
            synthetic = synthetic or text.lstrip().startswith(SYNTHETIC_PREFIXES)
            result.append(
                Message(
                    id=f"{turn.uuid or line}:{part}",
                    session=turn.sessionId or path.stem,
                    source=str(path),
                    line=line,
                    date=turn.timestamp,
                    role=actual,
                    text=text,
                    synthetic=synthetic,
                )
            )
    return result


def resolve(source: str, files: Files, home: Path) -> Path:
    if ":" not in source:
        return Path(source).expanduser().resolve()
    harness, identifier = source.split(":", 1)
    if harness != "claude" or not re.fullmatch(r"[0-9a-f-]{8,36}", identifier):
        raise ValueError(f"unsupported harness or malformed session identifier: {source}")
    matches = files.locate(home / ".claude/projects", f"*/{identifier}*.jsonl")
    if len(matches) != 1:
        raise ValueError(f"resolve {source}: expected one transcript, found {len(matches)}")
    return matches[0]


def load(path: Path, files: Files) -> list[Message]:
    raw = files.read(path)
    if path.suffix == ".json":
        from pydantic import TypeAdapter

        return TypeAdapter(list[Message]).validate_json(raw)
    return native_messages(raw, path)


def windows(messages: list[Message], limit: int, overlap: int) -> list[list[Message]]:
    if limit < 1 or overlap < 0 or overlap >= limit:
        raise ValueError("window limit must exceed nonnegative overlap")
    parts: list[Message] = []
    for message in messages:
        if message.synthetic or message.role == "system":
            continue
        for offset in range(0, len(message.text), limit):
            parts.append(message.model_copy(update={"text": message.text[offset : offset + limit]}))
    result: list[list[Message]] = []
    start = 0
    while start < len(parts):
        end = start
        size = 0
        while end < len(parts) and size + len(parts[end].text) <= limit:
            size += len(parts[end].text)
            end += 1
        result.append(parts[start:end])
        if end == len(parts):
            break
        next_start = end
        carried = 0
        while next_start > start + 1 and carried + len(parts[next_start - 1].text) <= overlap:
            next_start -= 1
            carried += len(parts[next_start].text)
        start = next_start
    return result
