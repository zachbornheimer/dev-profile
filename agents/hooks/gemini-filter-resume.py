#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Stop hook — auto-resume after a Gemini safety/content filter block.

When a turn stops because Gemini blocked the request ("blocked by Gemini's
filters" or "Request blocked by Google"), step through a three-stop ladder
per session:
  1. First filter stop: block Stop with reason "please continue".
  2. Second consecutive filter stop: block Stop with the last user request
     restated from the transcript.
  3. Third consecutive filter stop: allow the stop (fall through).

Any non-filter Stop resets the ladder for that session so a later filter block
starts fresh at step 1.

Uses hook_common (Claude-shape Decision.block) so agent-hooks and omp's
run-agent-hooks.ts bridge both convert the block into a hidden continuation
turn. Fails open on any error.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))

from hook_common import Decision, HookEvent, HookSettings, run_hook

HOOK_NAME = "gemini-filter-resume"
OFF_ENV = "HC_GEMINI_FILTER_RESUME_OFF"
STATE_PREFIX = "gemini-filter-resume-"
FILTER_MARKERS = (
    "blocked by Gemini's filters",
    "Request blocked by Google",
    "Generation was blocked by content filters",
)
PLEASE_CONTINUE = "please continue"
RESTATE_FALLBACK = "Continue the original coding task in plain language."
RESTATE_PREFIX = "Continue the original coding task. Restated request:\n\n"
TAIL_BYTES = 256 * 1024
RESTATE_CAP = 4000
SAFE_ID = re.compile(r"[^A-Za-z0-9._-]+")
MESSAGE_KEYS = (
    "last_assistant_message",
    "lastAssistantMessage",
    "prompt_response",
    "promptResponse",
    "assistant_message",
    "assistantMessage",
    "message",
    "error",
    "terminationReason",
)
NON_USER_PREFIXES = (
    "<command-",
    "<local-command",
    "<system-reminder",
    "<task-notification",
    "<bash-",
    "Stop hook feedback:",
    "[Request interrupted by user",
    RESTATE_PREFIX,
)


def _safe_id(value: str) -> str:
    cleaned = SAFE_ID.sub("_", value.strip())[:120]
    return cleaned or "unknown"


def _counter_path(state_dir: Path, session_id: str) -> Path:
    return state_dir / f"{STATE_PREFIX}{_safe_id(session_id)}.count"


def _load_count(state_dir: Path, session_id: str) -> int:
    try:
        return int(_counter_path(state_dir, session_id).read_text().strip() or "0")
    except (OSError, ValueError):
        return 0


def _save_count(state_dir: Path, session_id: str, count: int) -> None:
    with contextlib.suppress(OSError):
        state_dir.mkdir(parents=True, exist_ok=True)
        _counter_path(state_dir, session_id).write_text(f"{count}\n")


def _reset_count(state_dir: Path, session_id: str) -> None:
    with contextlib.suppress(OSError):
        _counter_path(state_dir, session_id).unlink()


def is_filter_block(text: str) -> bool:
    return any(marker in text for marker in FILTER_MARKERS)


def _text_of(value: Any) -> str:
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
        for key in ("text", "content", "errorMessage", "error", "message"):
            found = _text_of(value.get(key))
            if found:
                return found
    return ""


def _unwrap_user(text: str) -> str:
    match = re.search(r"<USER_REQUEST>([\s\S]*?)</USER_REQUEST>", text)
    body = match.group(1) if match else text
    body = re.sub(r"<ADDITIONAL_METADATA>[\s\S]*?</ADDITIONAL_METADATA>", "", body)
    body = re.sub(
        r"<(hook_prompt|task-notification|system-reminder|hindsight_memory|hindsight_memories|hindsight_bank|relevant_memories|user_feedback|hindsight_knowledge|hindsight_knowledge_refresh|system-context|system-notice|machine_host)\b[\s\S]*?</\1>",
        "",
        body,
    )
    return body.strip()


def _read_tail_lines(path_value: str) -> list[str]:
    if not path_value:
        return []
    path = Path(os.path.expanduser(path_value))
    try:
        size = path.stat().st_size
        with path.open("rb") as handle:
            if size > TAIL_BYTES:
                handle.seek(size - TAIL_BYTES)
            data = handle.read()
    except OSError:
        return []
    text = data.decode("utf-8", errors="replace")
    if size > TAIL_BYTES:
        cut = text.find("\n")
        if cut != -1:
            text = text[cut + 1 :]
    return [line.strip() for line in text.splitlines() if line.strip()]


def _record_role_and_msg(row: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    row_type = row.get("type")
    if row_type == "message" and isinstance(row.get("message"), dict):
        msg = row["message"]
        return str(msg.get("role") or ""), msg
    if row_type in ("user", "assistant") and isinstance(row.get("message"), dict):
        return str(row_type), row["message"]
    role = row.get("role") or (row.get("message") or {}).get("role") or row_type
    if role == "USER_INPUT":
        return "user", row
    if role in ("model", "PLANNER_RESPONSE"):
        return "assistant", row
    if role in ("user", "assistant"):
        return str(role), row
    return "", row


def _transcript_state(path_value: str) -> tuple[bool, str]:
    """Return (last_assistant_was_filter_blocked, last_clean_user_request)."""
    lines = _read_tail_lines(path_value)
    last_assistant_blocked: bool | None = None
    last_user = ""
    for line in lines:
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if not isinstance(row, dict):
            continue
        role, msg = _record_role_and_msg(row)
        if role == "user":
            attribution = msg.get("attribution")
            if attribution is not None and attribution != "user":
                continue
            raw_text = _text_of(msg.get("content") if "content" in msg else msg.get("text"))
            clean = _unwrap_user(raw_text)
            if (
                clean
                and clean != PLEASE_CONTINUE
                and not is_filter_block(clean)
                and not clean.startswith(NON_USER_PREFIXES)
            ):
                last_user = clean
        elif role == "assistant":
            prose = _text_of(msg.get("content") if "content" in msg else msg.get("text"))
            err = _text_of(msg.get("errorMessage") or row.get("errorMessage") or row.get("error"))
            combined = f"{prose}\n{err}".strip()
            last_assistant_blocked = is_filter_block(combined)
    return bool(last_assistant_blocked), last_user


def _payload_texts(event: HookEvent) -> str:
    parts: list[str] = []
    extra = event.payload.get("extra")
    extra_map = extra if isinstance(extra, dict) else {}
    for key in MESSAGE_KEYS:
        for source in (event.payload, extra_map):
            text = _text_of(source.get(key))
            if text:
                parts.append(text)
    return "\n".join(parts)


def _restate_reason(last_user: str) -> str:
    task = last_user.strip()
    if not task or is_filter_block(task) or task == PLEASE_CONTINUE:
        return RESTATE_FALLBACK
    body = f"{task[:RESTATE_CAP]}…" if len(task) > RESTATE_CAP else task
    return f"{RESTATE_PREFIX}{body}"


def decide(event: HookEvent) -> Decision | None:
    if os.environ.get(OFF_ENV):
        return Decision.no_objection("gemini-filter-resume:off")
    reason = event.field("reason", "reason")
    if reason and reason not in ("end_turn", "error", "model_stop"):
        return Decision.no_objection(f"non-turn-stop:{reason}")

    session_id = event.session_id or event.field("conversationId", "conversation_id") or "unknown"
    settings = HookSettings.from_env()
    transcript_path = event.field("transcript_path", "transcriptPath")
    transcript_blocked, last_user = _transcript_state(transcript_path)
    payload_blocked = is_filter_block(_payload_texts(event))
    blocked = payload_blocked or transcript_blocked

    if not blocked:
        _reset_count(settings.state_dir, session_id)
        return Decision.no_objection("gemini-filter-resume:ok")

    count = _load_count(settings.state_dir, session_id)
    if count <= 0:
        _save_count(settings.state_dir, session_id, 1)
        return Decision.block(PLEASE_CONTINUE)
    if count == 1:
        _save_count(settings.state_dir, session_id, 2)
        return Decision.block(_restate_reason(last_user))
    return Decision.no_objection("gemini-filter-resume:exhausted")


if __name__ == "__main__":
    run_hook(HOOK_NAME, decide)
