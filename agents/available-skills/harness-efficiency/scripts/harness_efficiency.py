#!/usr/bin/env python3
"""Discover, index, and analyze coding-agent sessions for recurring waste.

Only Codex desktop sessions are indexed; there is no omp parser."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sqlite3
import sys
import tempfile
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

_PARSE_PATH = Path(__file__).resolve().parent / "he_parse.py"
_SPEC = importlib.util.spec_from_file_location("he_parse", _PARSE_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise ImportError(f"cannot load {_PARSE_PATH}")
parse = importlib.util.module_from_spec(_SPEC)
sys.modules["he_parse"] = parse
_SPEC.loader.exec_module(parse)

SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
    path TEXT PRIMARY KEY,
    mtime REAL NOT NULL,
    size INTEGER NOT NULL,
    harness TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    harness TEXT NOT NULL,
    session_id TEXT NOT NULL,
    path TEXT NOT NULL,
    workspace TEXT,
    model TEXT,
    started_at TEXT,
    ended_at TEXT,
    user_turns INTEGER NOT NULL DEFAULT 0,
    agent_turns INTEGER NOT NULL DEFAULT 0,
    tool_calls INTEGER NOT NULL DEFAULT 0,
    shell_commands INTEGER NOT NULL DEFAULT 0,
    errors INTEGER NOT NULL DEFAULT 0,
    retries INTEGER NOT NULL DEFAULT 0,
    subagents INTEGER NOT NULL DEFAULT 0,
    permission_stops INTEGER NOT NULL DEFAULT 0,
    file_reads INTEGER NOT NULL DEFAULT 0,
    searches INTEGER NOT NULL DEFAULT 0,
    tests INTEGER NOT NULL DEFAULT 0,
    compactions INTEGER NOT NULL DEFAULT 0,
    tokens_input INTEGER,
    tokens_output INTEGER,
    tokens_cache_read INTEGER,
    cost REAL,
    duration_s REAL,
    PRIMARY KEY (harness, session_id)
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY,
    harness TEXT NOT NULL,
    session_id TEXT NOT NULL,
    path TEXT NOT NULL,
    kind TEXT NOT NULL,
    value TEXT NOT NULL,
    seq INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_session ON events(harness, session_id, seq);
"""

HARNESS_GLOBS = {"codex": (".codex/sessions", "**/*.jsonl")}

SESSION_INT_FIELDS = (
    "user_turns",
    "agent_turns",
    "tool_calls",
    "shell_commands",
    "errors",
    "retries",
    "subagents",
    "permission_stops",
    "file_reads",
    "searches",
    "tests",
    "compactions",
)
SESSION_OPT_FIELDS = (
    "workspace",
    "model",
    "started_at",
    "ended_at",
    "tokens_input",
    "tokens_output",
    "tokens_cache_read",
    "cost",
    "duration_s",
)

REQUIRED_EVAL_CASES = (
    "discover_codex",
    "repeated_workflow_to_command",
    "skill_vs_command_vs_subagent",
    "instruction_bloat",
    "linear_dedupe",
    "research_cache_fresh",
    "research_cache_stale",
)

REPORT_TOP_N = 40
MAX_REPEATED_SHELL_TITLE_LEN = 80


@dataclass(frozen=True)
class Context:
    home: Path
    state: Path
    bundled_research: Path
    now: datetime


def load_context() -> Context:
    home = Path(os.environ.get("HE_HOME", str(Path.home())))
    default_state = Path.home() / ".local" / "state" / "harness-efficiency"
    state = Path(os.environ.get("HE_STATE", str(default_state)))
    bundled = Path(__file__).resolve().parent.parent / "references" / "research.json"
    return Context(
        home=home, state=state, bundled_research=bundled, now=datetime.now(UTC)
    )


def connect_index(ctx: Context) -> sqlite3.Connection:
    ctx.state.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(ctx.state / "index.sqlite")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def cutoff_dt(ctx: Context, days: int, since_last: bool) -> datetime:
    if since_last:
        last = ctx.state / "last_run.json"
        if last.is_file():
            try:
                ran = json.loads(last.read_text(encoding="utf-8")).get("ran_at")
            except (OSError, json.JSONDecodeError):
                ran = None
            if ran:
                return datetime.fromisoformat(str(ran))
    return ctx.now - timedelta(days=days)


def _count_glob(root: Path, pattern: str) -> int:
    if not root.exists():
        return 0
    return sum(1 for path in root.glob(pattern) if path.is_file())


def discover(ctx: Context, harness: str | None = None) -> list[dict[str, Any]]:
    wanted = {harness} if harness else None
    rows: list[dict[str, Any]] = []
    for name, (rel, pattern) in HARNESS_GLOBS.items():
        if wanted and name not in wanted:
            continue
        root = ctx.home / rel
        present = root.exists()
        count = _count_glob(root, pattern) if present else 0
        notes = ""
        rows.append(
            {
                "name": name,
                "present": present,
                "session_count": count,
                "path": str(root),
                "notes": notes,
            }
        )
    return rows


def list_sources(ctx: Context, harness: str | None) -> list[tuple[str, Path]]:
    wanted = {harness} if harness else None
    out: list[tuple[str, Path]] = []
    for name, (rel, pattern) in HARNESS_GLOBS.items():
        if wanted and name not in wanted:
            continue
        root = ctx.home / rel
        if not root.exists():
            continue
        for path in root.glob(pattern):
            if path.is_file():
                out.append((name, path))
    return out


def parse_source(name: str, path: Path) -> list[parse.Session]:
    if name == "codex":
        return [parse.parse_codex(path)]
    return []


def insert_session(conn: sqlite3.Connection, session: parse.Session) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO sessions (
            harness, session_id, path, workspace, model, started_at, ended_at,
            user_turns, agent_turns, tool_calls, shell_commands, errors, retries,
            subagents, permission_stops, file_reads, searches, tests, compactions,
            tokens_input, tokens_output, tokens_cache_read, cost, duration_s
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            session.harness,
            session.session_id,
            session.path,
            session.workspace,
            session.model,
            session.started_at,
            session.ended_at,
            session.user_turns,
            session.agent_turns,
            session.tool_calls,
            session.shell_commands,
            session.errors,
            session.retries,
            session.subagents,
            session.permission_stops,
            session.file_reads,
            session.searches,
            session.tests,
            session.compactions,
            session.tokens_input,
            session.tokens_output,
            session.tokens_cache_read,
            session.cost,
            session.duration_s,
        ),
    )
    for seq, event in enumerate(session.events):
        conn.execute(
            "INSERT INTO events (harness, session_id, path, kind, value, seq) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                session.harness,
                session.session_id,
                session.path,
                event.kind,
                event.value,
                seq,
            ),
        )


def index_sessions(
    ctx: Context,
    days: int = parse.DEFAULT_DAYS,
    since_last: bool = False,
    limit: int | None = None,
    harness: str | None = None,
) -> int:
    cutoff = cutoff_dt(ctx, days, since_last)
    cutoff_ts = cutoff.timestamp()
    sources: list[tuple[str, Path, float, int]] = []
    for name, path in list_sources(ctx, harness):
        try:
            stat = path.stat()
        except OSError:
            continue
        if stat.st_mtime < cutoff_ts:
            continue
        sources.append((name, path, stat.st_mtime, stat.st_size))
    sources.sort(key=lambda item: item[2], reverse=True)
    if limit is not None:
        sources = sources[:limit]
    conn = connect_index(ctx)
    indexed = 0
    try:
        for name, path, mtime, size in sources:
            prev = conn.execute(
                "SELECT mtime, size FROM files WHERE path = ?", (str(path),)
            ).fetchone()
            if prev and prev[0] == mtime and prev[1] == size:
                continue
            conn.execute("DELETE FROM events WHERE path = ?", (str(path),))
            conn.execute("DELETE FROM sessions WHERE path = ?", (str(path),))
            for session in parse_source(name, path):
                insert_session(conn, session)
                indexed += 1
            conn.execute(
                "INSERT OR REPLACE INTO files(path, mtime, size, harness) VALUES (?, ?, ?, ?)",
                (str(path), mtime, size, name),
            )
        conn.commit()
    finally:
        conn.close()
    return indexed


def fetch_sessions(conn: sqlite3.Connection) -> list[parse.Session]:
    sessions: list[parse.Session] = []
    for row in conn.execute("SELECT * FROM sessions"):
        session = parse.Session(
            harness=row["harness"],
            session_id=row["session_id"],
            path=row["path"],
        )
        for field in SESSION_OPT_FIELDS:
            setattr(session, field, row[field])
        for field in SESSION_INT_FIELDS:
            setattr(session, field, int(row[field] or 0))
        sessions.append(session)
    return sessions


def fetch_events(conn: sqlite3.Connection) -> list[tuple[str, str, str, str]]:
    rows = conn.execute(
        "SELECT harness, session_id, kind, value FROM events ORDER BY session_id, seq"
    )
    return [(row[0], row[1], row[2], row[3]) for row in rows]


def make_finding(
    kind: str,
    title: str,
    group: dict[str, Any],
    extra: dict[str, Any] | None = None,
    impact: str | None = None,
) -> dict[str, Any]:
    payload = dict(extra or {})
    payload["title"] = title
    primitive = parse.classify_primitive(kind, payload)
    finding: dict[str, Any] = {
        "id": parse.fingerprint(kind, title),
        "kind": kind,
        "occurrences": group["count"],
        "session_count": len(group["sessions"]),
        "sessions": sorted(group["sessions"]),
        "examples": [parse.redact(title)],
        "proposed_primitive": primitive,
        "proposed_fix": parse.FIX.get(primitive, ""),
        "why_primitive": parse.WHY.get(primitive, ""),
        "measured": True,
    }
    if group.get("harnesses"):
        finding["harnesses"] = sorted(group["harnesses"])
    if group.get("models"):
        finding["models"] = sorted(group["models"])
    if impact:
        finding["impact"] = impact
    return finding


def cluster_events(
    sessions: list[parse.Session],
    events: list[tuple[str, str, str, str]],
    event_kind: str,
    finding_kind: str,
    ngram: int,
) -> list[dict[str, Any]]:
    meta = {s.session_id: s for s in sessions}
    by_session: dict[str, list[str]] = defaultdict(list)
    for _harness, sid, kind, value in events:
        if kind == event_kind and value:
            by_session[sid].append(value)
    groups: dict[str, dict[str, Any]] = {}
    for sid, values in by_session.items():
        if ngram == 1:
            window = values
        else:
            window = [
                " && ".join(values[i : i + ngram])
                for i in range(len(values) - ngram + 1)
            ]
        session = meta.get(sid)
        for item in window:
            if finding_kind == "repeated_tool_seq" and parse.skip_repeated_tool_seq(
                item
            ):
                continue
            if (
                finding_kind == "repeated_shell"
                and len(item) > MAX_REPEATED_SHELL_TITLE_LEN
            ):
                continue
            group = groups.setdefault(
                item,
                {"sessions": set(), "count": 0, "harnesses": set(), "models": set()},
            )
            group["count"] += 1
            group["sessions"].add(sid)
            if session:
                group["harnesses"].add(session.harness)
                if session.model:
                    group["models"].add(session.model)
    findings = []
    for title, group in groups.items():
        if len(group["sessions"]) < parse.MIN_FINDING_SESSIONS:
            continue
        findings.append(make_finding(finding_kind, title, group))
    return findings


def cluster_corrections(
    sessions: list[parse.Session], events: list[tuple[str, str, str, str]]
) -> list[dict[str, Any]]:
    meta = {s.session_id: s for s in sessions}
    groups: dict[str, dict[str, Any]] = {}
    for _harness, sid, kind, value in events:
        if kind != "correction" or not value:
            continue
        if not parse.is_correction(value):
            continue
        key = value[: parse.CORRECTION_PREFIX].lower()
        group = groups.setdefault(
            key, {"sessions": set(), "count": 0, "harnesses": set(), "models": set()}
        )
        group["count"] += 1
        group["sessions"].add(sid)
        session = meta.get(sid)
        if session:
            group["harnesses"].add(session.harness)
            if session.model:
                group["models"].add(session.model)
    return [
        make_finding("correction", title, group)
        for title, group in groups.items()
        if len(group["sessions"]) >= parse.MIN_FINDING_SESSIONS
    ]


def _sessions_finding(
    kind: str, title: str, chosen: list[parse.Session]
) -> dict[str, Any]:
    group = {
        "sessions": {s.session_id for s in chosen},
        "count": len(chosen),
        "harnesses": {s.harness for s in chosen},
        "models": {s.model for s in chosen if s.model},
    }
    impact = f"{len(chosen)} sessions"
    return make_finding(kind, title, group, impact=impact)


def cluster_session_flags(sessions: list[parse.Session]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    long = [
        s
        for s in sessions
        if (s.user_turns + s.agent_turns) >= parse.LONG_SESSION_TURNS
    ]
    if len(long) >= parse.MIN_FINDING_SESSIONS:
        findings.append(_sessions_finding("long_session", "long sessions", long))
    over: list[parse.Session] = []
    for session in sessions:
        non_test = max(session.shell_commands - session.tests, 0)
        if session.tests >= parse.TEST_OVERUSE_MIN and session.tests > (
            parse.TEST_OVERUSE_RATIO * max(non_test, 1)
        ):
            over.append(session)
    if len(over) >= parse.MIN_FINDING_SESSIONS:
        findings.append(_sessions_finding("test_overuse", "test overuse", over))
    perm = [s for s in sessions if s.permission_stops]
    if len(perm) >= parse.MIN_FINDING_SESSIONS:
        findings.append(_sessions_finding("permission_stop", "permission stops", perm))
    retry = [s for s in sessions if s.retries]
    if len(retry) >= parse.MIN_FINDING_SESSIONS:
        findings.append(_sessions_finding("retry", "retries", retry))
    compact = [s for s in sessions if s.compactions]
    if len(compact) >= parse.MIN_FINDING_SESSIONS:
        findings.append(_sessions_finding("compaction", "compactions", compact))
    spawned = [s for s in sessions if s.subagents >= parse.SUBAGENT_HIGH]
    if len(spawned) >= parse.MIN_FINDING_SESSIONS:
        findings.append(_sessions_finding("subagent", "high subagent spawn", spawned))
    return findings


def _line_count(path: str) -> int | None:
    try:
        with Path(path).open(encoding="utf-8", errors="replace") as handle:
            return sum(1 for _ in handle)
    except OSError:
        return None


def cluster_instruction_bloat(
    sessions: list[parse.Session], events: list[tuple[str, str, str, str]]
) -> list[dict[str, Any]]:
    meta = {s.session_id: s for s in sessions}
    groups: dict[str, dict[str, Any]] = {}
    for _harness, sid, kind, value in events:
        if kind != "read" or not value.endswith(parse.BLOAT_FILENAMES):
            continue
        group = groups.setdefault(
            value, {"sessions": set(), "count": 0, "harnesses": set(), "models": set()}
        )
        group["count"] += 1
        group["sessions"].add(sid)
        session = meta.get(sid)
        if session:
            group["harnesses"].add(session.harness)
            if session.model:
                group["models"].add(session.model)
    findings = []
    for path, group in groups.items():
        lines = _line_count(path)
        severe = (
            lines is not None
            and lines >= parse.INSTRUCTION_BLOAT_LINES
            and group["count"] >= 1
        )
        if len(group["sessions"]) < parse.MIN_FINDING_SESSIONS and not severe:
            continue
        impact = f"{len(group['sessions'])} sessions, {group['count']} reads"
        if lines is not None:
            impact += f", {lines} lines"
        finding = make_finding(
            "instruction_bloat",
            Path(path).name,
            group,
            extra={"path": path},
            impact=impact,
        )
        finding["examples"] = [parse.redact(path)]
        findings.append(finding)
    return findings


def cluster_model_routing(sessions: list[parse.Session]) -> list[dict[str, Any]]:
    expensive = []
    for session in sessions:
        if not session.model or session.user_turns > parse.TINY_SESSION_USER_TURNS:
            continue
        model = session.model.lower()
        if any(marker in model for marker in parse.EXPENSIVE_MODEL_MARKERS):
            expensive.append(session)
    if len(expensive) < parse.MIN_FINDING_SESSIONS:
        return []
    return [_sessions_finding("model_routing", "tiny expensive sessions", expensive)]


def load_prior_ids(ctx: Context) -> set[str]:
    path = ctx.state / "prior_findings.jsonl"
    ids: set[str] = set()
    if not path.is_file():
        return ids
    with path.open(encoding="utf-8", errors="replace") as handle:
        for raw in handle:
            raw = raw.strip()
            if not raw:
                continue
            try:
                obj = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict) and obj.get("id"):
                ids.add(str(obj["id"]))
    return ids


def join_prior(
    findings: list[dict[str, Any]], prior_ids: set[str]
) -> list[dict[str, Any]]:
    current = {f["id"] for f in findings}
    for finding in findings:
        finding["status"] = "still_present" if finding["id"] in prior_ids else "new"
    gone = []
    for pid in sorted(prior_ids - current):
        gone.append(
            {
                "id": pid,
                "kind": pid.split(":", 1)[0],
                "status": "gone",
                "occurrences": 0,
                "session_count": 0,
                "sessions": [],
                "examples": [],
                "proposed_primitive": "none",
                "proposed_fix": "",
                "why_primitive": "",
                "measured": True,
            }
        )
    return findings + gone


def write_outputs(
    run_dir: Path, findings: list[dict[str, Any]], sessions: list[parse.Session]
) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    ranked = sorted(
        findings,
        key=lambda item: (
            -int(item.get("session_count") or 0),
            str(item.get("id") or ""),
        ),
    )
    (run_dir / "patterns.json").write_text(
        json.dumps(ranked, indent=2) + "\n", encoding="utf-8"
    )
    total = len(ranked)
    shown = ranked[:REPORT_TOP_N]
    lines = [
        "# Harness efficiency",
        "",
        f"Sessions indexed: {len(sessions)}",
        f"Findings: {total}",
        f"Showing {REPORT_TOP_N} of {total}; full list in patterns.json",
        "",
        "| id | kind | sessions | primitive | status |",
        "|----|------|----------|-----------|--------|",
    ]
    for finding in shown:
        lines.append(
            f"| {finding['id']} | {finding['kind']} | "
            f"{finding.get('session_count', 0)} | "
            f"{finding.get('proposed_primitive', '')} | "
            f"{finding.get('status', '')} |"
        )
    lines.append("")
    (run_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def analyze(ctx: Context, run_dir: Path | None = None) -> list[dict[str, Any]]:
    conn = connect_index(ctx)
    try:
        sessions = fetch_sessions(conn)
        events = fetch_events(conn)
    finally:
        conn.close()
    findings: list[dict[str, Any]] = []
    findings.extend(cluster_events(sessions, events, "shell", "repeated_shell", 1))
    findings.extend(cluster_events(sessions, events, "shell", "repeated_shell", 2))
    findings.extend(cluster_events(sessions, events, "read", "repeated_read", 1))
    findings.extend(cluster_events(sessions, events, "search", "repeated_search", 1))
    findings.extend(cluster_events(sessions, events, "tool", "repeated_tool_seq", 3))
    findings.extend(cluster_corrections(sessions, events))
    findings.extend(cluster_session_flags(sessions))
    findings.extend(cluster_instruction_bloat(sessions, events))
    findings.extend(cluster_model_routing(sessions))
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for finding in findings:
        if finding["id"] in seen:
            continue
        seen.add(finding["id"])
        unique.append(finding)
    unique = join_prior(unique, load_prior_ids(ctx))
    if run_dir is not None:
        write_outputs(run_dir, unique, sessions)
    return unique


def stamp_research(ctx: Context) -> None:
    ctx.state.mkdir(parents=True, exist_ok=True)
    (ctx.state / "research_overlay.json").write_text(
        json.dumps({"checked_at": ctx.now.date().isoformat()}) + "\n",
        encoding="utf-8",
    )


def research_status(ctx: Context) -> dict[str, Any]:
    bundled = json.loads(ctx.bundled_research.read_text(encoding="utf-8"))
    ttl = int(bundled.get("ttl_days") or parse.RESEARCH_TTL_DAYS)
    checked_raw = bundled.get("checked_at")
    overlay = ctx.state / "research_overlay.json"
    if overlay.is_file():
        try:
            data = json.loads(overlay.read_text(encoding="utf-8"))
            if data.get("checked_at"):
                checked_raw = data["checked_at"]
        except (OSError, json.JSONDecodeError):
            pass
    checked = datetime.fromisoformat(str(checked_raw)[:10]).date()
    age = (ctx.now.date() - checked).days
    fresh = age < ttl
    stale_reason = (
        None
        if fresh
        else f"checked_at {checked.isoformat()} is {age} days old (ttl {ttl})"
    )
    return {
        "fresh": fresh,
        "checked_at": checked.isoformat(),
        "ttl_days": ttl,
        "stale_reason": stale_reason,
    }


def append_prior(ctx: Context, findings: list[dict[str, Any]]) -> None:
    existing = load_prior_ids(ctx)
    path = ctx.state / "prior_findings.jsonl"
    with path.open("a", encoding="utf-8") as handle:
        for finding in findings:
            if finding.get("status") == "gone" or finding["id"] in existing:
                continue
            handle.write(
                json.dumps({"id": finding["id"], "kind": finding.get("kind")}) + "\n"
            )


def new_run_dir(ctx: Context) -> Path:
    stamp = ctx.now.strftime("%Y%m%dT%H%M%SZ")
    run_dir = ctx.state / "runs" / stamp
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def audit(
    ctx: Context,
    days: int,
    since_last: bool,
    limit: int | None,
    harness: str | None,
    refresh_research: bool,
) -> Path:
    if refresh_research:
        stamp_research(ctx)
    disc = discover(ctx, harness=harness)
    research = research_status(ctx)
    indexed = index_sessions(
        ctx, days=days, since_last=since_last, limit=limit, harness=harness
    )
    run_dir = new_run_dir(ctx)
    findings = analyze(ctx, run_dir=run_dir)
    manifest = {
        "ran_at": ctx.now.isoformat(),
        "days": days,
        "indexed": indexed,
        "discover": disc,
        "research": research,
        "finding_count": len(findings),
    }
    (run_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    (ctx.state / "last_run.json").write_text(
        json.dumps(
            {"ran_at": ctx.now.isoformat(), "days": days, "run_dir": str(run_dir)},
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    append_prior(ctx, findings)
    return run_dir


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def write_eval_fixtures(home: Path) -> Path:
    agents_md = home / "AGENTS.md"
    agents_md.write_text(
        "\n".join(f"# rule {i}" for i in range(210)) + "\n", encoding="utf-8"
    )
    for index in range(3):
        path = (
            home
            / ".codex"
            / "sessions"
            / "2026"
            / "09"
            / "18"
            / f"rollout-{index}.jsonl"
        )
        rows = [
            {
                "type": "session_meta",
                "timestamp": "2026-09-18T12:00:00Z",
                "payload": {"cwd": "/repo", "id": f"codex-eval-{index}"},
            },
            {"type": "turn_context", "payload": {"model": "gpt-5"}},
            {
                "type": "response_item",
                "payload": {
                    "role": "user",
                    "content": [{"type": "input_text", "text": "check the tree"}],
                },
            },
        ]
        for call_id, name, arguments in (
            ("1", "shell", {"command": "git status --short"}),
            ("2", "shell", {"command": "git diff"}),
            ("3", "read", {"file_path": str(agents_md)}),
        ):
            rows.append(
                {
                    "type": "response_item",
                    "payload": {
                        "role": "assistant",
                        "type": "function_call",
                        "call_id": call_id,
                        "name": name,
                        "arguments": json.dumps(arguments),
                    },
                }
            )
            rows.append(
                {
                    "type": "response_item",
                    "timestamp": "2026-09-18T12:01:00Z",
                    "payload": {
                        "type": "function_call_output",
                        "call_id": call_id,
                        "output": "ok",
                    },
                }
            )
        _write_jsonl(path, rows)
    return agents_md


def _restore_env(key: str, value: str | None) -> None:
    if value is None:
        os.environ.pop(key, None)
    else:
        os.environ[key] = value


def eval_discover(disc: list[dict[str, Any]]) -> dict[str, Any]:
    ok = (
        len(disc) == 1
        and disc[0]["name"] == "codex"
        and (disc[0].get("present") and disc[0].get("session_count", 0) == 3)
    )
    return {"ok": bool(ok), "detail": "ok" if ok else f"unexpected discovery: {disc}"}


def eval_repeated(findings: list[dict[str, Any]]) -> dict[str, Any]:
    hits = [
        finding
        for finding in findings
        if finding.get("kind") in {"repeated_shell", "repeated_tool_seq"}
        and finding.get("session_count", 0) >= 3
        and finding.get("proposed_primitive") == "command"
    ]
    return {
        "ok": bool(hits),
        "detail": hits[0]["id"] if hits else "no repeated_shell/tool_seq",
    }


def eval_bloat(findings: list[dict[str, Any]]) -> dict[str, Any]:
    hits = [
        finding
        for finding in findings
        if finding.get("kind") == "instruction_bloat"
        and finding.get("proposed_primitive") in {"removal", "skill"}
    ]
    return {
        "ok": bool(hits),
        "detail": hits[0]["id"] if hits else "no instruction_bloat",
    }


def eval_classify() -> dict[str, Any]:
    checks = [
        (parse.classify_primitive("repeated_shell"), "command"),
        (parse.classify_primitive("instruction", {"always_on": False}), "skill"),
        (parse.classify_primitive("repeated_search", {"isolation": True}), "subagent"),
    ]
    bad = [f"{got!r}!={want!r}" for got, want in checks if got != want]
    return {"ok": not bad, "detail": "ok" if not bad else ", ".join(bad)}


def eval_linear() -> dict[str, Any]:
    titles = [
        ("ZYS-790", "gates cost"),
        ("ZYS-790", "gate-hours vs edit-hours"),
    ]
    hit = parse.match_existing("gates cost", titles)
    hit2 = parse.match_existing("gate-hours vs edit-hours", titles)
    miss = parse.match_existing("unrelated pineapple harvest", titles)
    ok = hit == "ZYS-790" and hit2 == "ZYS-790" and miss is None
    return {"ok": ok, "detail": f"hit={hit} hit2={hit2} miss={miss}"}


def eval_research_fresh(ctx: Context) -> dict[str, Any]:
    stamp_research(ctx)
    info = research_status(ctx)
    return {"ok": info.get("fresh") is True, "detail": json.dumps(info)}


def eval_research_stale(ctx: Context) -> dict[str, Any]:
    old = (ctx.now.date() - timedelta(days=20)).isoformat()
    (ctx.state / "research_overlay.json").write_text(
        json.dumps({"checked_at": old}) + "\n", encoding="utf-8"
    )
    info = research_status(ctx)
    return {"ok": info.get("fresh") is False, "detail": json.dumps(info)}


def run_eval() -> dict[str, Any]:
    old_home = os.environ.get("HE_HOME")
    old_state = os.environ.get("HE_STATE")
    cases: dict[str, Any] = {}
    try:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            home = tmp_path / "home"
            state = tmp_path / "state"
            home.mkdir()
            state.mkdir()
            os.environ["HE_HOME"] = str(home)
            os.environ["HE_STATE"] = str(state)
            write_eval_fixtures(home)
            ctx = load_context()
            disc = discover(ctx)
            cases["discover_codex"] = eval_discover(disc)
            index_sessions(ctx, days=parse.DEFAULT_DAYS)
            run_dir = state / "runs" / "eval"
            findings = analyze(ctx, run_dir=run_dir)
            cases["repeated_workflow_to_command"] = eval_repeated(findings)
            cases["instruction_bloat"] = eval_bloat(findings)
            cases["skill_vs_command_vs_subagent"] = eval_classify()
            cases["linear_dedupe"] = eval_linear()
            cases["research_cache_fresh"] = eval_research_fresh(ctx)
            cases["research_cache_stale"] = eval_research_stale(ctx)
    finally:
        _restore_env("HE_HOME", old_home)
        _restore_env("HE_STATE", old_state)
    passed = all(case.get("ok") for case in cases.values()) and set(cases) >= set(
        REQUIRED_EVAL_CASES
    )
    return {"passed": passed, "cases": cases}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="harness_efficiency")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_disc = sub.add_parser("discover")
    p_disc.add_argument("--json", action="store_true")
    p_disc.add_argument("--harness")
    p_idx = sub.add_parser("index")
    p_idx.add_argument("--days", type=int, default=parse.DEFAULT_DAYS)
    p_idx.add_argument("--since-last", action="store_true")
    p_idx.add_argument("--limit", type=int)
    p_idx.add_argument("--harness")
    sub.add_parser("analyze")
    p_res = sub.add_parser("research")
    p_res.add_argument("--json", action="store_true")
    p_res.add_argument("--stamp", action="store_true")
    p_audit = sub.add_parser("audit")
    p_audit.add_argument("--days", type=int, default=parse.DEFAULT_DAYS)
    p_audit.add_argument("--since-last", action="store_true")
    p_audit.add_argument("--limit", type=int)
    p_audit.add_argument("--harness")
    p_audit.add_argument("--refresh-research", action="store_true")
    sub.add_parser("eval")
    args = parser.parse_args(argv)
    if args.cmd == "eval":
        result = run_eval()
        print(json.dumps(result, indent=2))
        return 0 if result.get("passed") else 1
    ctx = load_context()
    if args.cmd == "discover":
        print(json.dumps(discover(ctx, harness=args.harness), indent=2))
        return 0
    if args.cmd == "index":
        count = index_sessions(
            ctx,
            days=args.days,
            since_last=args.since_last,
            limit=args.limit,
            harness=args.harness,
        )
        print(json.dumps({"indexed": count}))
        return 0
    if args.cmd == "analyze":
        run_dir = new_run_dir(ctx)
        findings = analyze(ctx, run_dir=run_dir)
        print(json.dumps({"finding_count": len(findings), "run_dir": str(run_dir)}))
        print(f"run_dir={run_dir}")
        return 0
    if args.cmd == "research":
        if args.stamp:
            stamp_research(ctx)
        print(json.dumps(research_status(ctx), indent=2))
        return 0
    if args.cmd == "audit":
        run_dir = audit(
            ctx,
            days=args.days,
            since_last=args.since_last,
            limit=args.limit,
            harness=args.harness,
            refresh_research=args.refresh_research,
        )
        print(f"run_dir={run_dir}")
        return 0
    parser.error(f"unknown command {args.cmd}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
