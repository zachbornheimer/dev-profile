#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Stream AI-tool session corrections as NDJSON to stdout.
Usage: uv run harvest-corrections.py [--days N] [--tool claude|codex|cursor|opencode|all]"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator, Protocol


# Patterns ordered from strongest signal to weakest; the first match wins.
_CORRECTION_RE = re.compile(
    r"(?im)^no[,\s!]|^nope[,\s!]|^actually[,\s]"
    r"|\bthat'?s (?:wrong|not right|incorrect)\b"
    r"|\byou (?:missed|forgot|didn'?t)\b|\bi (?:told|said|asked) you\b"
    r"|\bdon'?t do\b|\bstop (?:doing|using|writing|calling|adding)\b"
    r"|\bstill (?:doing|using|making|not)\b|\byou keep\b|\bplease don'?t\b"
)

_CURSOR_QUERY_RE = re.compile(r"<user_query>(.*?)</user_query>", re.DOTALL)
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
        return datetime.now(tz=timezone.utc)

    def home(self) -> Path:
        return Path.home()


@dataclass
class Correction:
    text: str             # full correction text (capped at _MAX_TEXT)
    context: str          # first _CTX_LEN chars, newlines collapsed
    tool: str             # claude-code | codex | cursor | opencode
    repo_or_project: str  # best available project path or identifier
    approx_date: str      # YYYY-MM-DD or "unknown"


def _is_correction(text: str) -> bool:
    if _MACHINE_RE.search(text):
        return False
    return _MIN_TEXT <= len(text) <= _MAX_TEXT and bool(_CORRECTION_RE.search(text))


def _normalize(content: str | list) -> str:
    """Flatten content blocks (Anthropic API format or plain string) to text."""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") in ("text", "input_text", None):
                parts.append(item.get("text", ""))
        return " ".join(parts).strip()
    return ""


def _ctx(text: str) -> str:
    return text[:_CTX_LEN].replace("\n", " ")

def _fp(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]

def _mtime(p: Path) -> datetime:
    return datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc)

def _skip(msg: str) -> None:
    print(f"skip: {msg}", file=sys.stderr)

def _jsonl(path: Path) -> Iterator[dict]:
    """Stream parsed JSON objects; skip malformed lines."""
    with path.open(encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            if raw := raw.strip():
                try:
                    yield json.loads(raw)
                except json.JSONDecodeError:
                    pass


def harvest_claude(env: _Env, cutoff: datetime) -> Iterator[Correction]:
    root = env.home() / ".claude" / "projects"
    if not root.is_dir():
        _skip("claude-code: ~/.claude/projects not found")
        return
    for proj in root.iterdir():
        if not proj.is_dir():
            continue
        repo = proj.name.lstrip("-").replace("-", "/")
        for jsonl in proj.glob("*.jsonl"):
            if _mtime(jsonl) < cutoff:
                continue
            try:
                for obj in _jsonl(jsonl):
                    if obj.get("type") != "user":
                        continue
                    msg = obj.get("message") or {}
                    text = _normalize(msg.get("content", "") if isinstance(msg, dict) else "")
                    if not _is_correction(text):
                        continue
                    ts = (obj.get("timestamp") or "")[:10] or "unknown"
                    yield Correction(text[:_MAX_TEXT], _ctx(text), "claude-code", repo, ts)
            except Exception as exc:
                _skip(f"claude-code {jsonl.name}: {exc}")


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
                    yield Correction(text[:_MAX_TEXT], _ctx(text), "codex", cwd or jsonl.parent.name, ts)
        except Exception as exc:
            _skip(f"codex {jsonl.name}: {exc}")


def harvest_cursor(env: _Env, cutoff: datetime) -> Iterator[Correction]:
    root = env.home() / ".cursor" / "chats"
    if not root.is_dir():
        _skip("cursor: ~/.cursor/chats not found")
        return
    for db in sorted(root.rglob("store.db")):
        if db.stat().st_size < 512 or _mtime(db) < cutoff:
            continue
        try:
            conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True, check_same_thread=False)
            try:
                rows = conn.execute("SELECT data FROM blobs").fetchall()
            finally:
                conn.close()
            for (raw,) in rows:
                if not isinstance(raw, bytes):
                    continue
                try:
                    obj = json.loads(raw.decode("utf-8", errors="replace"))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue
                if not isinstance(obj, dict) or obj.get("role") != "user":
                    continue
                text = _normalize(obj.get("content", ""))
                # Cursor injects <user_query>…</user_query> around the real text.
                if m := _CURSOR_QUERY_RE.search(text):
                    text = m.group(1).strip()
                if _is_correction(text):
                    yield Correction(text[:_MAX_TEXT], _ctx(text), "cursor", db.parent.parent.name, "unknown")
        except Exception as exc:
            _skip(f"cursor {db.parent.name}: {exc}")


def harvest_opencode(env: _Env, cutoff: datetime) -> Iterator[Correction]:
    db_path = env.home() / ".local" / "share" / "opencode" / "opencode.db"
    if not db_path.exists():
        _skip("opencode: db not found at ~/.local/share/opencode/opencode.db")
        return
    try:
        cutoff_ms = int(cutoff.timestamp() * 1_000)
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, check_same_thread=False)
        _SQL = ("SELECT m.time_created, p.data, pr.worktree FROM message m "
                "JOIN part p ON p.message_id = m.id "
                "LEFT JOIN session s ON s.id = m.session_id "
                "LEFT JOIN project pr ON pr.id = s.project_id "
                "WHERE json_extract(m.data,'$.role')='user' "
                "AND json_extract(p.data,'$.type')='text' AND m.time_created>=?")
        try:
            rows = conn.execute(_SQL, (cutoff_ms,)).fetchall()
        finally:
            conn.close()
        for ts_ms, part_raw, worktree in rows:
            try:
                text = (json.loads(part_raw).get("text") or "").strip()
            except json.JSONDecodeError:
                continue
            if not _is_correction(text):
                continue
            approx = datetime.fromtimestamp(ts_ms / 1_000, tz=timezone.utc).date().isoformat()
            yield Correction(text[:_MAX_TEXT], _ctx(text), "opencode", worktree or "unknown", approx)
    except Exception as exc:
        _skip(f"opencode: {exc}")


_HARVESTERS = {
    "claude": harvest_claude, "codex": harvest_codex,
    "cursor": harvest_cursor, "opencode": harvest_opencode,
}


def _dedup(it: Iterator[Correction]) -> Iterator[Correction]:
    seen: set[str] = set()
    for c in it:
        if (fp := _fp(c.text)) not in seen:
            seen.add(fp)
            yield c


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--days", type=int, default=7, metavar="N", help="Look-back window in days (default: 7)")
    ap.add_argument("--tool", choices=[*_HARVESTERS, "all"], default="all", help="Restrict to one tool")
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
    print(f"done: {count} unique candidates from the last {args.days} day(s)", file=sys.stderr)


if __name__ == "__main__":
    main()
