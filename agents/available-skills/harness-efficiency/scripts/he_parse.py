"""Codex session parser and primitive classifiers for harness-efficiency."""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime
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
BLOAT_FILENAMES = ("AGENTS.md",)
EXPENSIVE_MODEL_MARKERS = ("gpt-5-pro", "gpt-5.1-pro", "gpt-5.2-pro")
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
SLUG_RE = re.compile(r"[^a-z0-9]+")
TEST_CMD_RE = re.compile(r"(go test|pytest|mise run test|npm test|vitest|cargo test)")
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
            yield (
                str(item.get("id") or item.get("identifier") or ""),
                str(item.get("title") or ""),
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
    return str(data.get("command") or data.get("cmd") or data.get("commandLine") or "")


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


def _parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value)


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


def _note_user_text(session: Session, text: str) -> None:
    if is_correction(text):
        session.events.append(Event("correction", redact(text)))


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
