#!/usr/bin/env python3
"""Gated probe: does Grok deliver hook additionalContext on UPS vs PreToolUse?"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STATE_DIR = Path.home() / ".agents" / "hooks" / "state"
ENABLE_FLAG = STATE_DIR / "pick-probe.enable"
LOG_PATH = STATE_DIR / "pick-probe.log"
STDIN_TIMEOUT_SECS = 2

EVENT_USER_PROMPT_SUBMIT = "UserPromptSubmit"
EVENT_PRE_TOOL_USE = "PreToolUse"
MARKER_UPS = "PICKPROBE_UPS_a845a1bc"
MARKER_PRETOOL = "PICKPROBE_PRETOOL_a845a1bc"
EVENT_ALIASES = {
    "userpromptsubmit": EVENT_USER_PROMPT_SUBMIT,
    "user_prompt_submit": EVENT_USER_PROMPT_SUBMIT,
    "pretooluse": EVENT_PRE_TOOL_USE,
    "pre_tool_use": EVENT_PRE_TOOL_USE,
}
EVENT_TOKENS = {
    EVENT_USER_PROMPT_SUBMIT: MARKER_UPS,
    EVENT_PRE_TOOL_USE: MARKER_PRETOOL,
}


def read_stdin_json() -> dict[str, Any]:
    try:
        import select

        if not select.select([sys.stdin], [], [], STDIN_TIMEOUT_SECS)[0]:
            return {}
        raw = sys.stdin.read()
        if not raw:
            return {}
        payload = json.loads(raw)
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def event_name_of(payload: dict[str, Any]) -> str:
    for key in ("hook_event_name", "hookEventName"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            raw = value.strip()
            return EVENT_ALIASES.get(raw.lower(), raw)
    return ""


def append_log(event: str, token: str) -> None:
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        marker = token or "-"
        with LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(f"{now}\t{event or 'unknown'}\t{marker}\n")
    except OSError:
        return


def emit_allow(event: str, token: str) -> None:
    print(
        json.dumps(
            {
                "decision": "allow",
                "hookSpecificOutput": {
                    "hookEventName": event,
                    "additionalContext": token,
                },
            }
        )
    )


def main() -> int:
    if not ENABLE_FLAG.is_file():
        return 0
    payload = read_stdin_json()
    event = event_name_of(payload)
    token = EVENT_TOKENS.get(event, "")
    append_log(event, token)
    if token:
        emit_allow(event, token)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (KeyError, AttributeError, TypeError, ValueError, OSError):
        sys.exit(0)
