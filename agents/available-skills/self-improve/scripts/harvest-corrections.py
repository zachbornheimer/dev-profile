#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Stream corrections from Codex desktop session histories as NDJSON to stdout.
Only Codex sessions are harvested; there is no omp reader.
Usage: uv run harvest-corrections.py [--days N] [--tool codex|all]"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import re
import sys
from collections.abc import Iterator
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol

# Patterns ordered from strongest signal to weakest; the first match wins.
_CORRECTION_RE = re.compile(
    r"(?im)^no[,\s!]|^nope[,\s!]|^actually[,\s]"
    r"|\bthat'?s (?:wrong|not right|incorrect)\b"
    r"|\byou (?:missed|forgot|didn'?t)\b|\bi (?:told|said|asked) you\b"
    r"|\bdon'?t do\b|\bstop (?:doing|using|writing|calling|adding)\b"
    r"|\bstill (?:doing|using|making|not)\b|\byou keep\b|\bplease don'?t\b"
)

_MIN_TEXT, _MAX_TEXT, _CTX_LEN = 10, 2_000, 200  # floor, ceiling, context window

# Harness-injected user-role events (task notifications, slash-command echoes,
# system reminders) are not human corrections; drop them before pattern-matching.
_MACHINE_RE = re.compile(
    r"<task-notification>|\[SYSTEM NOTIFICATION|<system-reminder>"
    r"|<local-command-stdout>|<command-name>|<a2a-message>"
)


class _Env(Protocol):
    def now(self) -> datetime: ...
    def home(self) -> Path: ...


class _SystemEnv:
    def now(self) -> datetime:
        return datetime.now(tz=UTC)

    def home(self) -> Path:
        return Path.home()


@dataclass
class Correction:
    text: str  # full correction text (capped at _MAX_TEXT)
    context: str  # first _CTX_LEN chars, newlines collapsed
    tool: str  # codex
    repo_or_project: str  # best available project path or identifier
    approx_date: str  # YYYY-MM-DD or "unknown"


def _is_correction(text: str) -> bool:
    if _MACHINE_RE.search(text):
        return False
    return _MIN_TEXT <= len(text) <= _MAX_TEXT and bool(_CORRECTION_RE.search(text))


def _normalize(content: str | list) -> str:
    """Flatten content blocks (input text blocks or plain string) to text."""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") in (
                "text",
                "input_text",
                None,
            ):
                parts.append(item.get("text", ""))
        return " ".join(parts).strip()
    return ""


def _ctx(text: str) -> str:
    return text[:_CTX_LEN].replace("\n", " ")


def _fp(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def _mtime(p: Path) -> datetime:
    return datetime.fromtimestamp(p.stat().st_mtime, tz=UTC)


def _skip(msg: str) -> None:
    print(f"skip: {msg}", file=sys.stderr)


def _jsonl(path: Path) -> Iterator[dict]:
    """Stream parsed JSON objects; skip malformed lines."""
    with path.open(encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            if raw := raw.strip():
                with contextlib.suppress(json.JSONDecodeError):
                    yield json.loads(raw)


def harvest_codex(env: _Env, cutoff: datetime) -> Iterator[Correction]:
    root = env.home() / ".codex" / "sessions"
    if not root.is_dir():
        _skip("codex: ~/.codex/sessions not found")
        return
    for jsonl in sorted(root.rglob("*.jsonl")):
        if _mtime(jsonl) < cutoff:
            continue
        try:
            cwd = ""
            for obj in _jsonl(jsonl):
                if obj.get("type") == "session_meta":
                    cwd = (obj.get("payload") or {}).get("cwd", "")
                elif obj.get("type") == "response_item":
                    pl = obj.get("payload") or {}
                    if pl.get("role") != "user":
                        continue
                    text = _normalize(pl.get("content", []))
                    if not _is_correction(text):
                        continue
                    ts = (obj.get("timestamp") or "")[:10] or "unknown"
                    yield Correction(
                        text[:_MAX_TEXT],
                        _ctx(text),
                        "codex",
                        cwd or jsonl.parent.name,
                        ts,
                    )
        except Exception as exc:
            _skip(f"codex {jsonl.name}: {exc}")


_HARVESTERS = {"codex": harvest_codex}


def _dedup(it: Iterator[Correction]) -> Iterator[Correction]:
    seen: set[str] = set()
    for c in it:
        if (fp := _fp(c.text)) not in seen:
            seen.add(fp)
            yield c


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--days",
        type=int,
        default=7,
        metavar="N",
        help="Look-back window in days (default: 7)",
    )
    ap.add_argument(
        "--tool",
        choices=[*_HARVESTERS, "all"],
        default="all",
        help="Restrict to one tool",
    )
    args = ap.parse_args()

    env = _SystemEnv()
    cutoff = env.now() - timedelta(days=args.days)
    tools = list(_HARVESTERS) if args.tool == "all" else [args.tool]

    def _stream() -> Iterator[Correction]:
        for name in tools:
            yield from _HARVESTERS[name](env, cutoff)

    count = 0
    for c in _dedup(_stream()):
        print(json.dumps(asdict(c), ensure_ascii=False))
        count += 1
    print(
        f"done: {count} unique candidates from the last {args.days} day(s)",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
