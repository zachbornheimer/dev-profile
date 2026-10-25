#!/usr/bin/env python3
"""Resolve any Claude Code session identifier to its transcript path.

Usage:
    find-session.py <identifier>

<identifier> may be a full sessionId, a sessionId prefix, an exact session
name, a substring of a session name (case-insensitive), a jobId, or a pid —
resolution tries each of those six rules in order and stops at the first
that produces a match — or a cross-harness form agentmux is the index for:
"<harness>:<uuid>" (grok, codex, cursor — claude-code:<uuid> is accepted too
and just strips the prefix), or a bare uuid only agentmux's own link records
know about.

The registry at ~/.claude/sessions/*.json only holds sessions that are
still running. A session that has ended leaves no registry entry but its
transcript file remains, so when the registry yields nothing this script
falls back to globbing ~/.claude/projects/*/<identifier>*.jsonl.

Every Claude match is then enriched with an "agentmux" key — that session's
`agentmux session claude-code:<uuid> --json` result (project id, combined
transcript, every sibling session) — when the `agentmux` binary is on PATH
and resolves it; silently omitted otherwise (missing binary, non-zero exit,
or no project has linked the session yet).

Prints one JSON object per match to stdout, newest (by transcript mtime)
first, and exits 0. Prints a diagnostic naming what was searched to
stderr and exits 1 when nothing matches.

Override the home directory for testing with SESSIONS_HOME.
"""

from __future__ import annotations

import glob
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

HOME = Path(os.environ.get("SESSIONS_HOME", os.path.expanduser("~")))
SESSIONS_DIR = HOME / ".claude" / "sessions"
PROJECTS_DIR = HOME / ".claude" / "projects"

# Non-Claude harnesses agentmux is the index for (REQ-050). "claude-code" is
# accepted too, as a prefix to strip before this script's own six rules run.
AGENTMUX_HARNESS_PREFIXES = ("claude-code", "codex", "cursor", "grok")

# agentmux_call_timeout_seconds bounds one `agentmux session ... --json`
# subprocess call — a filesystem-backed lookup, not a network one, so a
# generous bound only guards against a genuinely wedged process.
AGENTMUX_CALL_TIMEOUT_SECONDS = 10


def cwd_to_project_slug(cwd: str) -> str:
    """Mirror Claude Code's own project-directory naming: every character
    that isn't alphanumeric becomes a dash."""
    return "".join(ch if ch.isalnum() else "-" for ch in cwd)


def load_registry() -> list[dict]:
    """Every parsed ~/.claude/sessions/*.json entry, skipping unparsable ones."""
    entries = []
    for path in sorted(SESSIONS_DIR.glob("*.json")):
        try:
            entries.append(json.loads(path.read_text()))
        except (json.JSONDecodeError, OSError):
            continue
    return entries


def transcript_path_for(entry: dict) -> Path | None:
    session_id = entry.get("sessionId")
    cwd = entry.get("cwd")
    if not session_id or not cwd:
        return None
    slug = cwd_to_project_slug(cwd)
    path = PROJECTS_DIR / slug / f"{session_id}.jsonl"
    return path if path.exists() else None


def subagent_dir_for(entry: dict, transcript: Path) -> str | None:
    session_id = entry.get("sessionId")
    candidate = transcript.parent / session_id / "subagents"
    return str(candidate) if candidate.is_dir() else None


def registry_match_to_result(entry: dict, transcript: Path, matched_by: str) -> dict:
    result = {
        "transcript_path": str(transcript),
        "session_id": entry.get("sessionId"),
        "name": entry.get("name"),
        "cwd": entry.get("cwd"),
        "status": entry.get("status"),
        "kind": entry.get("kind"),
        "started_at": entry.get("startedAt"),
        "size_bytes": transcript.stat().st_size,
        "mtime": transcript.stat().st_mtime,
        "matched_by": matched_by,
    }
    subagent_dir = subagent_dir_for(entry, transcript)
    if subagent_dir:
        result["subagent_dir"] = subagent_dir
    return result


def find_in_registry(identifier: str) -> list[dict]:
    """Try the five registry-backed resolution rules in priority order.
    Returns as soon as a rule produces any match — rules don't merge."""
    entries = load_registry()

    rules = [
        ("exact_session_id", lambda e: e.get("sessionId") == identifier),
        (
            "session_id_prefix",
            lambda e: (e.get("sessionId") or "").startswith(identifier),
        ),
        ("exact_name", lambda e: e.get("name") == identifier),
        (
            "name_substring",
            lambda e: identifier.lower() in (e.get("name") or "").lower(),
        ),
        ("job_id", lambda e: e.get("jobId") == identifier),
        ("pid", lambda e: str(e.get("pid")) == identifier),
    ]

    for matched_by, predicate in rules:
        matches = []
        for entry in entries:
            if not predicate(entry):
                continue
            transcript = transcript_path_for(entry)
            if transcript is None:
                continue
            matches.append(registry_match_to_result(entry, transcript, matched_by))
        if matches:
            return matches
    return []


def find_by_transcript_glob(identifier: str) -> list[dict]:
    """Fallback for ended sessions: the registry entry is gone but the
    transcript file is still on disk under its slugified project directory."""
    pattern = str(PROJECTS_DIR / "*" / f"*{identifier}*.jsonl")
    results = []
    for path_str in glob.glob(pattern):
        path = Path(path_str)
        session_id = path.stem
        results.append(
            {
                "transcript_path": str(path),
                "session_id": session_id,
                "name": None,
                "cwd": None,
                "status": "ended",
                "kind": None,
                "started_at": None,
                "size_bytes": path.stat().st_size,
                "mtime": path.stat().st_mtime,
                "matched_by": "transcript_glob",
            }
        )
    return results


def agentmux_session_json(ref: str) -> dict | None:
    """Runs `agentmux session <ref> --json` and returns its parsed object,
    or None for any reason it can't be trusted (binary missing, non-zero
    exit, a timeout, or unparsable output) — never raises, per this
    script's "skip silently" contract for the agentmux enrichment."""
    if shutil.which("agentmux") is None:
        return None
    try:
        proc = subprocess.run(
            ["agentmux", "session", ref, "--json"],
            capture_output=True,
            text=True,
            timeout=AGENTMUX_CALL_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None


def attach_agentmux(matches: list[dict]) -> None:
    """Enriches each Claude match in place with its agentmux cross-harness
    view, keyed by the match's own full session id (REQ-050)."""
    for match in matches:
        session_id = match.get("session_id")
        if not session_id:
            continue
        summary = agentmux_session_json(f"claude-code:{session_id}")
        if summary is not None:
            match["agentmux"] = summary


def agentmux_session_entry(summary: dict, session_id: str) -> dict | None:
    for entry in summary.get("sessions", []):
        if entry.get("harness_session_id") == session_id:
            return entry
    return None


def resolve_via_agentmux(ref: str, session_id: str) -> dict | None:
    """Resolves a session agentmux knows about but this script's own
    Claude-only rules and glob fallback do not (REQ-050): a non-Claude
    harness ref, or a bare uuid only agentmux's link records carry."""
    summary = agentmux_session_json(ref)
    if summary is None:
        return None
    entry = agentmux_session_entry(summary, session_id)
    if entry is None:
        return None
    return {
        "transcript_path": entry.get("harness_transcript_path") or "",
        "session_id": session_id,
        "name": None,
        "cwd": None,
        "status": None,
        "kind": None,
        "started_at": entry.get("created_at"),
        "size_bytes": None,
        "mtime": None,
        "matched_by": "agentmux",
        "agentmux": summary,
    }


def split_harness_ref(identifier: str) -> tuple[str, str] | None:
    """Splits "<harness>:<uuid>" when harness is one agentmux registers
    (REQ-050); None for a bare identifier, which every other rule in this
    script treats as a local (Claude) lookup first."""
    harness_name, sep, session_id = identifier.partition(":")
    if sep and harness_name in AGENTMUX_HARNESS_PREFIXES and session_id:
        return harness_name, session_id
    return None


def resolve(identifier: str) -> list[dict]:
    harness_ref = split_harness_ref(identifier)
    local_identifier = identifier
    if harness_ref:
        harness_name, session_id = harness_ref
        if harness_name != "claude-code":
            result = resolve_via_agentmux(identifier, session_id)
            return [result] if result else []
        local_identifier = session_id

    matches = find_in_registry(local_identifier)
    if not matches:
        matches = find_by_transcript_glob(local_identifier)
    if matches:
        attach_agentmux(matches)
        return matches

    # A bare uuid (or claude-code:<uuid>) none of the six local rules
    # matched: agentmux's own link records may still know it.
    result = resolve_via_agentmux(local_identifier, local_identifier)
    return [result] if result else []


def main() -> int:
    if len(sys.argv) != 2:
        print(
            "Usage: find-session.py <session-id | name-substring | jobId | pid | <harness>:<uuid>>",
            file=sys.stderr,
        )
        return 1

    identifier = sys.argv[1]
    matches = resolve(identifier)

    if not matches:
        print(
            f"No session matched '{identifier}'. Searched sessionId, sessionId "
            f"prefix, name, name substring, jobId, and pid in {SESSIONS_DIR}, "
            f"globbed {PROJECTS_DIR}/*/*{identifier}*.jsonl, and asked agentmux's "
            f"cross-harness session index. Nothing found.",
            file=sys.stderr,
        )
        return 1

    matches.sort(key=lambda m: m.get("mtime") or 0, reverse=True)
    for match in matches:
        print(json.dumps(match))
    return 0


if __name__ == "__main__":
    sys.exit(main())
