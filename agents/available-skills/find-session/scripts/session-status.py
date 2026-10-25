#!/usr/bin/env python3
"""Report whether a Claude session is busy from its transcript tail.

Usage:
    session-status.py <identifier>

<identifier> is anything find-session.py accepts. Status comes from the last
parseable JSONL event, not from ListAgents or the live registry: a session-end
event means the session is not busy.

Override the home directory for testing with SESSIONS_HOME.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

TAIL_READ_BYTES = 64 * 1024

# Claude writes type "ended-by-model" when the model ends the session.
# Tests and forensics also name the same fact "session-end".
SESSION_END_EVENT_TYPES = frozenset(
    {
        "session-end",
        "session_end",
        "ended-by-model",
    }
)
SYSTEM_EVENT_TYPE = "system"

STATUS_ENDED = "ended"
STATUS_BUSY = "busy"


def event_is_session_end(event: dict) -> bool:
    event_type = event.get("type")
    if event_type in SESSION_END_EVENT_TYPES:
        return True
    return (
        event_type == SYSTEM_EVENT_TYPE
        and event.get("subtype") in SESSION_END_EVENT_TYPES
    )


def event_is_busy(event: dict | None) -> bool:
    if event is None:
        return False
    return not event_is_session_end(event)


def last_event(path: Path) -> dict | None:
    """Last parseable JSONL object, reading from the tail so large transcripts
    are not loaded whole."""
    with path.open("rb") as handle:
        handle.seek(0, os.SEEK_END)
        size = handle.tell()
        if size == 0:
            return None
        remaining = size
        buffer = b""
        while remaining > 0:
            chunk = min(TAIL_READ_BYTES, remaining)
            remaining -= chunk
            handle.seek(remaining)
            buffer = handle.read(chunk) + buffer
            lines = buffer.split(b"\n")
            candidates = lines if remaining == 0 else lines[1:]
            for raw in reversed(candidates):
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    parsed = json.loads(raw.decode("utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue
                if isinstance(parsed, dict):
                    return parsed
        return None


def _load_find_session():
    path = Path(__file__).resolve().parent / "find-session.py"
    spec = importlib.util.spec_from_file_location("find_session", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def status_for_identifier(identifier: str) -> dict:
    finder = _load_find_session()
    matches = finder.resolve(identifier)
    if not matches:
        raise FileNotFoundError(f"No session matched {identifier!r}")
    matches.sort(key=lambda match: match.get("mtime") or 0, reverse=True)
    match = matches[0]
    transcript = match.get("transcript_path")
    if not transcript:
        raise FileNotFoundError(f"Session {identifier!r} has no transcript path")
    path = Path(transcript)
    try:
        event = last_event(path)
    except OSError as error:
        raise OSError(
            f"cannot read transcript {path} for {identifier!r}: {error}"
        ) from error
    busy = event_is_busy(event)
    result = {
        "session_id": match.get("session_id"),
        "transcript_path": str(path),
        "busy": busy,
        "status": STATUS_BUSY if busy else STATUS_ENDED,
        "last_event_type": None if event is None else event.get("type"),
    }
    subtype = None if event is None else event.get("subtype")
    if subtype:
        result["last_event_subtype"] = subtype
    return result


def main() -> int:
    if len(sys.argv) != 2:
        print(
            "Usage: session-status.py <session-id | name-substring | jobId | pid>",
            file=sys.stderr,
        )
        return 1

    identifier = sys.argv[1]
    try:
        payload = status_for_identifier(identifier)
    except FileNotFoundError as error:
        print(str(error), file=sys.stderr)
        return 1
    except OSError as error:
        print(str(error), file=sys.stderr)
        return 1

    print(json.dumps(payload))
    return 0


if __name__ == "__main__":
    sys.exit(main())
