"""Session parsers and primitive classifiers for harness-efficiency."""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_DAYS = 14
RESEARCH_TTL_DAYS = 7
EVENT_VALUE_MAX = 200
CORRECTION_PREFIX = 80
MIN_FINDING_SESSIONS = 3
LONG_SESSION_TURNS = 80
TEST_OVERUSE_RATIO = 3
TEST_OVERUSE_MIN = 10
INSTRUCTION_BLOAT_LINES = 200
TINY_SESSION_USER_TURNS = 2
SUBAGENT_HIGH = 3
BLOAT_FILENAMES = ("CLAUDE.md", "AGENTS.md")
EXPENSIVE_MODEL_MARKERS = ("opus",)
INJECTED_CONTEXT_PREFIXES = ("user-info", "os version", "<role>", "you are ")
EXPLORE_SEQ_TOKENS = frozenset({"read", "search", "list-dir"})
EXPLORE_LOOP_TOKENS = frozenset({"read", "search", "list-dir", "glob", "grep"})

CORRECTION_RE = re.compile(
    r"(?im)^no[,\s!]|that's (wrong|not right)|you (missed|forgot)|don't do|"
    r"you keep|still (doing|using)"
)
SECRET_RE = re.compile(
    r"(?i)sk-[a-z0-9_-]+|ghp_[a-z0-9]+|xai-[a-z0-9_-]+|akia[a-z0-9]+|"
    r"(?:bearer|token)[:\s]+[a-z0-9._\-]+"
)
TMP_PATH_RE = re.compile(r"/tmp/\S+|/var/folders/\S+")
USER_QUERY_RE = re.compile(r"<user_query>(.*?)</user_query>", re.DOTALL)
SLUG_RE = re.compile(r"[^a-z0-9]+")
TEST_CMD_RE = re.compile(
    r"(go test|pytest|mise run test|npm test|vitest|cargo test)"
)
WS_RE = re.compile(r"\s+")

SHELL_NAMES = frozenset({"bash", "shell", "run_terminal_command", "command"})
READ_NAMES = frozenset({"read", "read_file", "readfile"})
SEARCH_NAMES = frozenset({"grep", "glob", "codebase_search", "semantic_search"})
AGENT_NAMES = frozenset({"agent", "task", "spawn_subagent"})
COMPACT_NAMES = frozenset({"compact", "compaction"})
COMPACT_TYPES = frozenset({"compact", "compaction"})

KIND_PRIMITIVE = {
    "repeated_shell": "command",
    "repeated_read": "command",
    "repeated_search": "skill",
    "repeated_tool_seq": "command",
    "correction": "skill",
    "permission_stop": "hook",
    "retry": "hook",
    "compaction": "none",
    "subagent": "none",
    "test_overuse": "command",
    "long_session": "subagent",
    "instruction_bloat": "removal",
    "model_routing": "config",
    "skill_self": "skill",
    "instruction": "skill",
}

WHY = {
    "command": "script if no judgment",
    "skill": "on-demand procedure",
    "subagent": "raw output would wreck the parent",
    "hook": "must fire even if the model forgets",
    "rule": "always-true fact",
    "removal": "fix or remove an existing instruction before adding another",
    "config": "harness or model setting",
    "zq": "CLI output belongs to zq / Evident Output",
    "none": "no change",
}

FIX = {
    "command": "Wrap the repeated command sequence in a script or slash command.",
    "skill": "Encode the on-demand procedure as a skill; keep AGENTS.md for facts only.",
    "subagent": "Run the dump or search in a subagent and return a summary.",
    "hook": "Enforce with a hook (token-free, mandatory).",
    "rule": "State the fact once in AGENTS.md.",
    "removal": "Trim the always-on file; move procedures into a skill.",
    "config": "Route tiny sessions off expensive models.",
    "zq": "Use zq / Evident Output for this CLI.",
    "none": "No change.",
}


@dataclass
class Event:
    kind: str
    value: str


@dataclass
class Session:
    harness: str
    session_id: str
    path: str
    workspace: str | None = None
    model: str | None = None
    started_at: str | None = None
    ended_at: str | None = None
    user_turns: int = 0
    agent_turns: int = 0
    tool_calls: int = 0
    shell_commands: int = 0
    errors: int = 0
    retries: int = 0
    subagents: int = 0
    permission_stops: int = 0
    file_reads: int = 0
    searches: int = 0
    tests: int = 0
    compactions: int = 0
    tokens_input: int | None = None
    tokens_output: int | None = None
    tokens_cache_read: int | None = None
    cost: float | None = None
    duration_s: float | None = None
    events: list[Event] = field(default_factory=list)


class _ToolTrack:
    def __init__(self) -> None:
        self.last_name = ""
        self.last_errored = False

    def on_tool(self, session: Session, name: str) -> None:
        if self.last_errored and name == self.last_name:
            session.retries += 1
        self.last_name = name
        self.last_errored = False

    def on_error(self, session: Session) -> None:
        session.errors += 1
        self.last_errored = True


def redact(text: str) -> str:
    return SECRET_RE.sub("<redacted>", text)[:EVENT_VALUE_MAX]


def normalize_shell(command: str) -> str:
    command = WS_RE.sub(" ", command).strip()
    command = TMP_PATH_RE.sub("<tmp>", command)
    return command[:EVENT_VALUE_MAX]


def is_correction(text: str) -> bool:
    lowered = text.lstrip().lower()
    if lowered.startswith(INJECTED_CONTEXT_PREFIXES):
        return False
    return bool(CORRECTION_RE.search(text))


def unwrap_user_query(text: str) -> str:
    match = USER_QUERY_RE.search(text)
    return match.group(1).strip() if match else text


def tool_seq_tokens(title: str) -> list[str]:
    return [
        part.strip().lower().replace("_", "-")
        for part in title.split("&&")
        if part.strip()
    ]


def skip_repeated_tool_seq(title: str) -> bool:
    tokens = tool_seq_tokens(title)
    if not tokens:
        return False
    unique = set(tokens)
    return len(unique) == 1 or unique <= EXPLORE_LOOP_TOKENS


def classify_primitive(kind: str, extra: dict[str, Any] | None = None) -> str:
    extra = extra or {}
    if extra.get("isolation") or extra.get("dump"):
        return "subagent"
    if kind == "repeated_tool_seq":
        tokens = tool_seq_tokens(str(extra.get("title") or ""))
        unique = set(tokens)
        if tokens and (len(unique) == 1 or unique <= EXPLORE_SEQ_TOKENS):
            return "subagent"
    if extra.get("always_on") is True:
        return "rule"
    if (
        kind in {"instruction", "procedure"}
        or extra.get("procedure")
        or extra.get("on_demand")
    ):
        return "skill"
    if kind == "instruction_bloat":
        path = str(extra.get("path") or "")
        if path.endswith("SKILL.md"):
            return "skill"
        return "removal"
    return KIND_PRIMITIVE.get(kind, "none")


def fingerprint(kind: str, title: str) -> str:
    slug = SLUG_RE.sub("-", title.lower()).strip("-")[:80] or "unknown"
    return f"{kind}:{slug}"


def _words(text: str) -> set[str]:
    return set(SLUG_RE.split(text.lower())) - {""}


def _pairs(existing_titles: list[Any]) -> Iterator[tuple[str, str]]:
    for item in existing_titles:
        if isinstance(item, str):
            bits = item.split(None, 1)
            if len(bits) == 2 and bits[0].startswith("ZYS-"):
                yield bits[0], bits[1]
            else:
                yield "", item
        elif isinstance(item, dict):
            yield str(item.get("id") or item.get("identifier") or ""), str(
                item.get("title") or ""
            )
        else:
            yield str(item[0]), str(item[1])


def _gates_overlap(query: str, title: str) -> bool:
    title_hit = "gate" in title and any(w in title for w in ("cost", "edit", "hours"))
    query_hit = "gate" in query and any(w in query for w in ("cost", "edit", "hours"))
    return title_hit and query_hit


def match_existing(fingerprint_or_title: str, existing_titles: list[Any]) -> str | None:
    query = fingerprint_or_title.lower()
    query_words = _words(query.replace(":", " "))
    for issue_id, title in _pairs(existing_titles):
        title_l = title.lower()
        if issue_id and _gates_overlap(query, title_l):
            return issue_id
        if issue_id and len(query_words & _words(title)) >= 2:
            return issue_id
    return None


def flatten_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") in {
                "text",
                "input_text",
                None,
            }:
                parts.append(str(block.get("text") or ""))
        return " ".join(parts)
    return ""


def has_tool_result(content: Any) -> bool:
    if isinstance(content, list):
        return any(
            isinstance(block, dict) and block.get("type") == "tool_result"
            for block in content
        )
    return False


def iter_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    with path.open(encoding="utf-8", errors="replace") as handle:
        for raw in handle:
            raw = raw.strip()
            if not raw:
                continue
            try:
                obj = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                yield obj


def _as_dict(inp: Any) -> dict[str, Any]:
    if isinstance(inp, str):
        try:
            parsed = json.loads(inp)
        except json.JSONDecodeError:
            return {"command": inp}
        return parsed if isinstance(parsed, dict) else {"command": inp}
    return inp if isinstance(inp, dict) else {}


def _input_command(inp: Any) -> str:
    data = _as_dict(inp)
    return str(
        data.get("command") or data.get("cmd") or data.get("commandLine") or ""
    )


def _input_path(inp: Any) -> str:
    data = _as_dict(inp)
    return str(
        data.get("file_path") or data.get("path") or data.get("target_file") or ""
    )


def _input_query(inp: Any) -> str:
    data = _as_dict(inp)
    return str(
        data.get("pattern")
        or data.get("query")
        or data.get("glob_pattern")
        or data.get("glob")
        or ""
    )


def apply_tool(session: Session, track: _ToolTrack, name: str, inp: Any) -> None:
    session.tool_calls += 1
    lower = name.lower()
    track.on_tool(session, lower)
    if lower in COMPACT_NAMES:
        session.compactions += 1
        return
    if lower in AGENT_NAMES:
        session.subagents += 1
        session.events.append(Event("tool", redact(lower)))
        return
    if lower in SHELL_NAMES:
        command = normalize_shell(_input_command(inp))
        session.shell_commands += 1
        if TEST_CMD_RE.search(command):
            session.tests += 1
        session.events.append(Event("shell", redact(command)))
        session.events.append(Event("tool", "shell"))
        return
    if lower in READ_NAMES:
        path = _input_path(inp)
        session.file_reads += 1
        session.events.append(Event("read", redact(path)))
        session.events.append(Event("tool", "read"))
        return
    if lower in SEARCH_NAMES:
        query = _input_query(inp)
        session.searches += 1
        session.events.append(Event("search", redact(query)))
        session.events.append(Event("tool", "search"))
        return
    session.events.append(Event("tool", redact(lower)))


def apply_error(session: Session, track: _ToolTrack, text: str = "") -> None:
    track.on_error(session)
    blob = text.lower()
    session.events.append(Event("error", redact(text or "error")))
    if "permission" in blob and any(
        word in blob for word in ("denied", "rejected", "blocked")
    ):
        session.permission_stops += 1


def _walk_tool_blocks(
    session: Session, track: _ToolTrack, content: list[Any]
) -> None:
    for block in content:
        if not isinstance(block, dict):
            continue
        typ = block.get("type")
        if typ in {"tool_use", "tool_call", "function_call"}:
            apply_tool(
                session,
                track,
                str(block.get("name") or ""),
                block.get("input") or block.get("arguments") or {},
            )
        elif typ == "tool_result" or block.get("is_error"):
            text = flatten_text(block.get("content") or "")
            if block.get("is_error") or text.lower().startswith("error"):
                apply_error(session, track, text)


def _ingest_tool_results(
    session: Session, track: _ToolTrack, content: Any
) -> None:
    if not isinstance(content, list):
        return
    for block in content:
        if not isinstance(block, dict) or block.get("type") != "tool_result":
            continue
        text = flatten_text(block.get("content") or block.get("text") or "")
        if block.get("is_error") or text.lower().startswith("error"):
            apply_error(session, track, text)


def _ingest_usage(session: Session, obj: dict[str, Any]) -> None:
    usage = obj.get("usage")
    if not isinstance(usage, dict):
        return
    inp = usage.get("input_tokens")
    out = usage.get("output_tokens")
    cache = usage.get("cache_read_input_tokens")
    if isinstance(inp, int):
        session.tokens_input = (session.tokens_input or 0) + inp
    if isinstance(out, int):
        session.tokens_output = (session.tokens_output or 0) + out
    if isinstance(cache, int):
        session.tokens_cache_read = (session.tokens_cache_read or 0) + cache


def _parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _set_duration(session: Session) -> None:
    if not session.started_at or not session.ended_at:
        return
    try:
        start = _parse_ts(str(session.started_at))
        end = _parse_ts(str(session.ended_at))
    except (TypeError, ValueError):
        return
    session.duration_s = max(0.0, (end - start).total_seconds())


def _stamp(session: Session, ts: Any) -> None:
    if not isinstance(ts, str) or not ts:
        return
    if not session.started_at:
        session.started_at = ts
    session.ended_at = ts


def _note_user_text(session: Session, text: str, unwrap: bool = False) -> None:
    if unwrap:
        text = unwrap_user_query(text)
    if is_correction(text):
        session.events.append(Event("correction", redact(text)))


def parse_claude(path: Path) -> Session:
    session = Session(harness="claude", session_id=path.stem, path=str(path))
    track = _ToolTrack()
    for obj in iter_jsonl(path):
        typ = obj.get("type")
        if typ in COMPACT_TYPES:
            session.compactions += 1
            continue
        if obj.get("cwd") and not session.workspace:
            session.workspace = str(obj["cwd"])
        _stamp(session, obj.get("timestamp"))
        if typ == "user":
            msg = obj.get("message") if isinstance(obj.get("message"), dict) else obj
            content = msg.get("content") if isinstance(msg, dict) else None
            if has_tool_result(content):
                _ingest_tool_results(session, track, content)
                continue
            session.user_turns += 1
            _note_user_text(session, flatten_text(content))
            continue
        if typ != "assistant":
            continue
        session.agent_turns += 1
        msg = obj.get("message") if isinstance(obj.get("message"), dict) else obj
        if isinstance(msg, dict):
            _ingest_usage(session, msg)
            content = msg.get("content")
            if isinstance(content, list):
                _walk_tool_blocks(session, track, content)
    _set_duration(session)
    return session


def parse_codex(path: Path) -> Session:
    session = Session(harness="codex", session_id=path.stem, path=str(path))
    track = _ToolTrack()
    for obj in iter_jsonl(path):
        typ = obj.get("type")
        payload = obj.get("payload") if isinstance(obj.get("payload"), dict) else {}
        _stamp(session, obj.get("timestamp"))
        if typ == "session_meta":
            cwd = payload.get("cwd")
            if cwd:
                session.workspace = str(cwd)
            sid = payload.get("id") or payload.get("session_id")
            if sid:
                session.session_id = str(sid)
            continue
        if typ == "turn_context":
            model = payload.get("model")
            if model:
                session.model = str(model)
            continue
        if typ in COMPACT_TYPES or payload.get("type") in COMPACT_TYPES:
            session.compactions += 1
            continue
        role = payload.get("role")
        ptype = payload.get("type")
        if role == "user":
            session.user_turns += 1
            _note_user_text(session, flatten_text(payload.get("content")))
            continue
        if role == "assistant":
            session.agent_turns += 1
        if ptype in {"function_call", "tool_call", "custom_tool_call"} or (
            payload.get("name") and ptype != "function_call_output"
        ):
            name = str(payload.get("name") or payload.get("tool") or "")
            if name:
                apply_tool(
                    session,
                    track,
                    name,
                    payload.get("arguments") or payload.get("input") or {},
                )
        if ptype in {"function_call_output", "tool_result"} or payload.get("is_error"):
            text = str(payload.get("output") or payload.get("content") or "")
            if payload.get("is_error") or text.lower().startswith("error"):
                apply_error(session, track, text)
    _set_duration(session)
    return session


def parse_cursor(path: Path) -> Session:
    session = Session(harness="cursor", session_id=path.parent.name, path=str(path))
    track = _ToolTrack()
    for obj in iter_jsonl(path):
        role = obj.get("role") or obj.get("type")
        message = obj.get("message") if isinstance(obj.get("message"), dict) else obj
        content = message.get("content") if isinstance(message, dict) else None
        if role in {"user", "human"}:
            session.user_turns += 1
            _note_user_text(session, flatten_text(content), unwrap=True)
            continue
        if role in {"assistant", "ai"}:
            session.agent_turns += 1
        if isinstance(content, list):
            _walk_tool_blocks(session, track, content)
    return session


def parse_grok(summary_path: Path) -> Session | None:
    try:
        summary = json.loads(
            summary_path.read_text(encoding="utf-8", errors="replace")
        )
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(summary, dict):
        return None
    if summary.get("session_kind") == "subagent":
        return None
    sid = str(summary.get("id") or summary_path.parent.name)
    session = Session(harness="grok", session_id=sid, path=str(summary_path))
    cwd = summary.get("cwd") or summary.get("working_directory")
    if cwd:
        session.workspace = str(cwd)
    model = summary.get("current_model_id") or summary.get("model")
    if model:
        session.model = str(model)
    started = summary.get("created_at") or summary.get("started_at")
    ended = summary.get("updated_at") or summary.get("ended_at")
    if started:
        session.started_at = str(started)
    if ended:
        session.ended_at = str(ended)
    track = _ToolTrack()
    history = summary_path.parent / "chat_history.jsonl"
    if history.is_file():
        for obj in iter_jsonl(history):
            if obj.get("synthetic_reason"):
                continue
            typ = obj.get("type") or obj.get("role")
            if typ in {"user", "human"}:
                session.user_turns += 1
                _note_user_text(session, flatten_text(obj.get("content")), unwrap=True)
            elif typ in {"assistant", "ai"}:
                session.agent_turns += 1
                for call in obj.get("tool_calls") or []:
                    if isinstance(call, dict):
                        apply_tool(
                            session,
                            track,
                            str(call.get("name") or ""),
                            call.get("arguments") or call.get("input") or {},
                        )
            elif typ in {"tool_result", "tool"}:
                err = obj.get("error") or obj.get("is_error")
                text = flatten_text(obj.get("content") or obj.get("output") or "")
                if err or text.lower().startswith("error"):
                    apply_error(session, track, str(err or text))
    _set_duration(session)
    return session


def parse_gemini(path: Path) -> Session:
    session = Session(harness="gemini", session_id=path.stem, path=str(path))
    first = True
    track = _ToolTrack()
    for obj in iter_jsonl(path):
        if first:
            first = False
            sid = obj.get("sessionId") or obj.get("session_id")
            if sid:
                session.session_id = str(sid)
            start = obj.get("startTime") or obj.get("start_time")
            if start:
                session.started_at = str(start)
            role = obj.get("role") or obj.get("type")
            if role not in {"user", "assistant", "model", "human", "ai"}:
                continue
        role = obj.get("role") or obj.get("type")
        if role in {"user", "human"}:
            session.user_turns += 1
            _note_user_text(
                session,
                flatten_text(obj.get("content") or obj.get("text") or obj.get("message")),
            )
        elif role in {"assistant", "model", "ai"}:
            session.agent_turns += 1
            content = obj.get("content")
            if isinstance(content, list):
                _walk_tool_blocks(session, track, content)
            for call in obj.get("tool_calls") or []:
                if isinstance(call, dict):
                    apply_tool(
                        session,
                        track,
                        str(call.get("name") or ""),
                        call.get("args") or call.get("input") or {},
                    )
    return session


def parse_copilot(path: Path) -> Session:
    session = Session(
        harness="copilot", session_id=path.parent.name, path=str(path)
    )
    meta = path.parent / "vscode.metadata.json"
    if meta.is_file():
        try:
            data = json.loads(meta.read_text(encoding="utf-8", errors="replace"))
        except (OSError, json.JSONDecodeError):
            data = {}
        if isinstance(data, dict):
            workspace = (
                data.get("workspace") or data.get("workspacePath") or data.get("cwd")
            )
            if workspace:
                session.workspace = str(workspace)
    track = _ToolTrack()
    for obj in iter_jsonl(path):
        role = obj.get("role") or obj.get("type")
        name = obj.get("name") or obj.get("tool") or ""
        if role in {"user", "human"}:
            session.user_turns += 1
            _note_user_text(
                session, flatten_text(obj.get("content") or obj.get("message") or "")
            )
        elif role in {"assistant", "ai", "model"}:
            session.agent_turns += 1
        if name and str(name) not in {"message", "user", "assistant"}:
            apply_tool(
                session,
                track,
                str(name),
                obj.get("input") or obj.get("arguments") or {},
            )
        if obj.get("is_error") or str(obj.get("error") or "").lower().startswith(
            "error"
        ):
            apply_error(session, track, str(obj.get("error") or "error"))
    return session


def _ms_iso(ms: Any) -> str | None:
    try:
        value = float(ms)
    except (TypeError, ValueError):
        return None
    if value > 10_000_000_000:
        value = value / 1000.0
    return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()


def _table_cols(conn: sqlite3.Connection, table: str) -> set[str]:
    try:
        return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    except sqlite3.Error:
        return set()


def _fill_opencode_parts(
    conn: sqlite3.Connection,
    session: Session,
    track: _ToolTrack,
    msg_id: Any,
    role: str,
) -> None:
    cols = _table_cols(conn, "part")
    if "message_id" not in cols or "data" not in cols:
        return
    try:
        parts = conn.execute(
            "SELECT data, json_extract(data, '$.type'), "
            "json_extract(data, '$.text') FROM part WHERE message_id = ?",
            (msg_id,),
        ).fetchall()
    except sqlite3.Error:
        return
    for data_raw, part_type, text in parts:
        if role in {"user", "human"} and part_type == "text" and text:
            _note_user_text(session, str(text))
        if part_type in {"tool", "tool_call", "tool_use"}:
            try:
                data = json.loads(data_raw) if isinstance(data_raw, str) else {}
            except json.JSONDecodeError:
                data = {}
            name = ""
            inp: Any = {}
            if isinstance(data, dict):
                name = str(data.get("name") or data.get("tool") or "")
                inp = data.get("input") or data.get("arguments") or data
            if name:
                apply_tool(session, track, name, inp)
        if part_type in {"tool_result", "error"} or (
            isinstance(text, str) and text.lower().startswith("error")
        ):
            apply_error(session, track, str(text or "error"))


def _fill_opencode_messages(conn: sqlite3.Connection, session: Session) -> None:
    cols = _table_cols(conn, "message")
    if "session_id" not in cols:
        return
    track = _ToolTrack()
    order = " ORDER BY time_created" if "time_created" in cols else ""
    data_col = "data" if "data" in cols else "NULL"
    try:
        rows = conn.execute(
            f"SELECT id, {data_col} FROM message WHERE session_id = ?{order}",
            (session.session_id,),
        ).fetchall()
    except sqlite3.Error:
        return
    for msg_id, raw in rows:
        role = ""
        if raw:
            try:
                data = json.loads(raw) if isinstance(raw, str) else {}
            except json.JSONDecodeError:
                data = {}
            if isinstance(data, dict):
                role = str(data.get("role") or "")
        if role in {"user", "human"}:
            session.user_turns += 1
        elif role in {"assistant", "ai"}:
            session.agent_turns += 1
        _fill_opencode_parts(conn, session, track, msg_id, role)


def parse_opencode_db(db_path: Path, cutoff_ms: int) -> list[Session]:
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except sqlite3.Error:
        return []
    try:
        cols = _table_cols(conn, "session")
        if not cols:
            return []
        wanted = [
            "id",
            "directory",
            "title",
            "model",
            "agent",
            "cost",
            "tokens_input",
            "tokens_output",
            "tokens_cache_read",
            "time_created",
            "time_updated",
            "time_compacting",
        ]
        select = ", ".join(
            name if name in cols else f"NULL AS {name}" for name in wanted
        )
        sql = f"SELECT {select} FROM session"
        params: tuple[Any, ...] = ()
        if "time_updated" in cols:
            sql += " WHERE time_updated >= ?"
            params = (cutoff_ms,)
        sessions: list[Session] = []
        for row in conn.execute(sql, params):
            rec = dict(zip(wanted, row))
            session = Session(
                harness="opencode",
                session_id=str(rec["id"]),
                path=str(db_path),
            )
            if rec.get("directory"):
                session.workspace = str(rec["directory"])
            if rec.get("model"):
                session.model = str(rec["model"])
            if rec.get("cost") is not None:
                try:
                    session.cost = float(rec["cost"])
                except (TypeError, ValueError):
                    pass
            for field_name, attr in (
                ("tokens_input", "tokens_input"),
                ("tokens_output", "tokens_output"),
                ("tokens_cache_read", "tokens_cache_read"),
            ):
                if rec.get(field_name) is not None:
                    try:
                        setattr(session, attr, int(rec[field_name]))
                    except (TypeError, ValueError):
                        pass
            created = rec.get("time_created")
            updated = rec.get("time_updated")
            if created:
                session.started_at = _ms_iso(created)
            if updated:
                session.ended_at = _ms_iso(updated)
            if created is not None and updated is not None:
                try:
                    session.duration_s = max(
                        0.0, (float(updated) - float(created)) / 1000.0
                    )
                except (TypeError, ValueError):
                    pass
            if rec.get("time_compacting"):
                session.compactions += 1
            _fill_opencode_messages(conn, session)
            sessions.append(session)
        return sessions
    except sqlite3.Error:
        return []
    finally:
        conn.close()
