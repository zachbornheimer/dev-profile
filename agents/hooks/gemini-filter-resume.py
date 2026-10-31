#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Antigravity Stop hook: one filter block gets "please continue", the next
gets the last user request restated, and a third block is allowed to stop.

Antigravity injects `reason` as a system message and cannot delete the
original prompt. A non-filter stop resets the ladder for that conversation.
Fails open: any parse or IO error allows the stop.
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from pathlib import Path

FILTER = "blocked by Gemini's filters"
PLEASE = "please continue"
TAIL_BYTES = 256 * 1024
RESTATE_CAP = 4000
SAFE_ID = re.compile(r"[^A-Za-z0-9._-]+")


def state_root() -> Path:
    override = os.environ.get("GEMINI_FILTER_RESUME_STATE")
    if override:
        return Path(override)
    return Path.home() / ".local" / "state" / "gemini-filter-resume"


def emit(payload: dict) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")


def safe_id(value: object) -> str:
    text = value if isinstance(value, str) and value else "unknown"
    cleaned = SAFE_ID.sub("_", text)[:120]
    return cleaned or "unknown"


def counter_path(conversation_id: str) -> Path:
    return state_root() / f"{conversation_id}.count"


def load_count(conversation_id: str) -> int:
    path = counter_path(conversation_id)
    try:
        return int(path.read_text().strip() or "0")
    except (OSError, ValueError):
        return 0


def save_count(conversation_id: str, count: int) -> None:
    root = state_root()
    root.mkdir(parents=True, exist_ok=True)
    counter_path(conversation_id).write_text(f"{count}\n")


def reset_count(conversation_id: str) -> None:
    try:
        counter_path(conversation_id).unlink()
    except FileNotFoundError:
        return
    except OSError:
        return


def text_of(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                part = item.get("text") or item.get("content")
                if isinstance(part, str):
                    parts.append(part)
        return "\n".join(parts)
    if isinstance(value, dict):
        for key in ("text", "content", "message"):
            found = text_of(value.get(key))
            if found:
                return found
    return ""


def unwrap_user(text: str) -> str:
    match = re.search(r"<USER_REQUEST>([\s\S]*?)</USER_REQUEST>", text)
    body = match.group(1) if match else text
    body = re.sub(r"<ADDITIONAL_METADATA>[\s\S]*?</ADDITIONAL_METADATA>", "", body)
    return body.strip()


def read_tail(path: Path) -> str:
    try:
        size = path.stat().st_size
    except OSError:
        return ""
    try:
        with path.open("rb") as handle:
            if size > TAIL_BYTES:
                handle.seek(size - TAIL_BYTES)
            data = handle.read()
    except OSError:
        return ""
    text = data.decode("utf-8", errors="replace")
    if size > TAIL_BYTES:
        cut = text.find("\n")
        if cut != -1:
            text = text[cut + 1 :]
    return text


def transcript_user_texts(path_value: object) -> list[str]:
    if not isinstance(path_value, str) or not path_value:
        return []
    texts: list[str] = []
    for line in read_tail(Path(os.path.expanduser(path_value))).splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        role = (
            event.get("role")
            or (event.get("message") or {}).get("role")
            or event.get("type")
        )
        if role not in ("user", "USER_INPUT"):
            continue
        content = event.get("content")
        if content is None:
            content = event.get("text")
        if content is None and isinstance(event.get("message"), dict):
            message = event["message"]
            content = (
                message.get("content")
                if message.get("content") is not None
                else message.get("text")
            )
        clean = unwrap_user(text_of(content))
        if clean and FILTER not in clean and clean != PLEASE:
            texts.append(clean)
    return texts


def blocked(event: dict) -> bool:
    error = event.get("error")
    if isinstance(error, str) and FILTER in error:
        return True
    reason = event.get("terminationReason")
    if isinstance(reason, str) and FILTER in reason:
        return True
    tail = (
        read_tail(Path(os.path.expanduser(event["transcriptPath"])))
        if isinstance(event.get("transcriptPath"), str)
        else ""
    )
    return FILTER in tail


def restate(event: dict) -> str:
    users = transcript_user_texts(event.get("transcriptPath"))
    task = users[-1] if users else ""
    if len(task) > RESTATE_CAP:
        task = task[:RESTATE_CAP] + "…"
    if not task:
        return (
            "Continue the original coding task in plain language. "
            "The transcript had no user request to restate."
        )
    return "Continue the original coding task. Restated request:\n\n" + task


def decide(event: dict) -> dict:
    conversation_id = safe_id(event.get("conversationId"))
    if not blocked(event):
        reset_count(conversation_id)
        return {"decision": "allow"}
    count = load_count(conversation_id)
    if count <= 0:
        save_count(conversation_id, 1)
        return {"decision": "continue", "reason": PLEASE}
    if count == 1:
        save_count(conversation_id, 2)
        return {"decision": "continue", "reason": restate(event)}
    return {"decision": "allow"}


def self_test() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["GEMINI_FILTER_RESUME_STATE"] = tmp
        transcript = Path(tmp) / "transcript.jsonl"
        transcript.write_text(
            json.dumps(
                {
                    "role": "user",
                    "content": "<USER_REQUEST>fix the parser</USER_REQUEST>",
                }
            )
            + "\n"
            + json.dumps(
                {
                    "role": "assistant",
                    "content": "This request was blocked by Gemini's filters.",
                }
            )
            + "\n"
        )
        event = {
            "conversationId": "conv-1",
            "error": "This request was blocked by Gemini's filters.",
            "transcriptPath": str(transcript),
        }
        first = decide(event)
        second = decide(event)
        third = decide(event)
        reset = decide(
            {"conversationId": "conv-1", "terminationReason": "model_stop", "error": ""}
        )
        again = decide(event)
        other = decide({"conversationId": "conv-2", "terminationReason": "model_stop"})
        checks = [
            first == {"decision": "continue", "reason": PLEASE},
            second.get("decision") == "continue"
            and "fix the parser" in second.get("reason", ""),
            "blocked by Gemini" not in second.get("reason", ""),
            third == {"decision": "allow"},
            reset == {"decision": "allow"},
            again == {"decision": "continue", "reason": PLEASE},
            other == {"decision": "allow"},
        ]
        if not all(checks):
            sys.stderr.write(
                json.dumps(
                    {
                        "first": first,
                        "second": second,
                        "third": third,
                        "reset": reset,
                        "again": again,
                        "other": other,
                    }
                )
                + "\n"
            )
            return 1
    return 0


def main() -> int:
    if "--self-test" in sys.argv[1:]:
        return self_test()
    try:
        raw = sys.stdin.read()
        event = json.loads(raw) if raw.strip() else {}
        if not isinstance(event, dict):
            emit({"decision": "allow"})
            return 0
        emit(decide(event))
    except Exception:
        emit({"decision": "allow"})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
