"""Where agent sessions live, which ones are recent, and how to read them as text.

Covers every harness cass indexes plus Cursor agent transcripts, which cass's
Cursor connector misses. External CLIs go through Shell so tests can fake them;
transcripts are read by the capability runtime's get_recent_turns workflow.
"""

from __future__ import annotations

import atexit
import json
import os
import re
import select
import subprocess
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

MAX_TRANSCRIPT_CHARS = int(os.environ.get("MEMORY_LEARN_MAX_CHARS", "60000"))
SWEEP_LIMIT = 200
CLI_TIMEOUT_SECONDS = 60
# cass agent slug -> get_recent_turns harness.
CAPABILITY_HARNESS = {
    "claude_code": "claude",
    "grok": "grok",
    "codex": "codex",
    "cursor": "cursor",
}
# The capability keeps whole turns newest-first until a bound bites. These
# make the character cap the only one that does, as the old reader's did.
TURNS_ALL = 10_000
MESSAGE_CHARS = 2_000
CHARS_PER_TOKEN = 4  # the capability's own estimate
SPEAKER_LABEL = {"user": "USER", "agent": "ASSISTANT"}  # system text is harness noise
UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
CODEX_ROLLOUT_ID = re.compile(rf"rollout-.*-(?P<id>{UUID})\.jsonl")
CURSOR_PROJECTS = Path.home() / ".cursor/projects"
CURSOR_TRANSCRIPT_GLOB = "*/agent-transcripts/*/*.jsonl"
HARNESS_DIR_AGENT = (
    ("/.grok/", "grok"),
    ("/.codex/", "codex"),
    ("/.cursor/", "cursor"),
)
# Undo the JSON string escapes that matter for matching quoted text.
JSON_ESCAPES = (
    ("\\n", "\n"),
    ("\\t", "\t"),
    ('\\"', '"'),
    ("\\u003e", ">"),
    ("\\u003c", "<"),
    ("\\u0026", "&"),
)
RELATIVE_SINCE = re.compile(r"-(?P<count>\d+)(?P<unit>[dh])")
SINCE_UNIT_SECONDS = {"d": 86_400, "h": 3_600}


@dataclass(frozen=True, slots=True)
class Session:
    path: str
    agent: str
    size: int = 0


class Shell:
    """The one seam to external CLIs and the capability runtime; tests substitute a fake."""

    def __init__(self) -> None:
        self._server: subprocess.Popen[bytes] | None = None
        self._inbox = b""
        self._next_id = 0

    def run(
        self,
        args: Sequence[str],
        *,
        stdin: str = "",
        timeout: float = CLI_TIMEOUT_SECONDS,
    ) -> str:
        done = subprocess.run(
            list(args),
            input=stdin,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        if done.returncode != 0:
            raise RuntimeError(
                f"{args[0]} exited {done.returncode}: {done.stderr.strip()[:300]}"
            )
        return done.stdout

    def capability(
        self, tool: str, arguments: dict, *, timeout: float = CLI_TIMEOUT_SECONDS
    ) -> dict:
        """Call one capability-runtime tool and return its JSON result.

        `capability run` knows only capabilities, not plain workflows such as
        get_recent_turns, and each run costs seconds of start-up. One long-lived
        `capability mcp` (JSON-RPC over stdio) serves every call of a sweep.
        """
        deadline = time.monotonic() + timeout
        if self._server is None or self._server.poll() is not None:
            self._start(deadline)
        reply = self._request(
            "tools/call", {"name": tool, "arguments": arguments}, deadline
        )
        text = "".join(block.get("text", "") for block in reply["content"])
        if reply.get("isError"):
            raise RuntimeError(f"capability {tool} failed: {text[:300]}")
        return json.loads(text)

    def close(self) -> None:
        if self._server is not None and self._server.poll() is None:
            self._server.kill()
            self._server.wait()
        self._server = None

    def _start(self, deadline: float) -> None:
        self._inbox = b""
        self._server = subprocess.Popen(
            ["capability", "mcp"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            bufsize=0,
        )
        atexit.register(self.close)
        client = {"name": "memory-learn", "version": "0"}
        self._request(
            "initialize",
            {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": client},
            deadline,
        )
        self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def _send(self, message: dict) -> None:
        assert self._server is not None and self._server.stdin is not None
        self._server.stdin.write(json.dumps(message).encode() + b"\n")

    def _request(self, method: str, params: dict, deadline: float) -> dict:
        self._next_id += 1
        wanted = self._next_id
        self._send(
            {"jsonrpc": "2.0", "id": wanted, "method": method, "params": params}
        )
        while True:
            line = self._read_line(deadline)
            try:
                message = json.loads(line)
            except ValueError:
                continue
            if message.get("id") != wanted:
                continue  # notifications and server-initiated requests
            if "error" in message:
                raise RuntimeError(f"capability mcp {method}: {message['error']}")
            return message["result"]

    def _read_line(self, deadline: float) -> bytes:
        assert self._server is not None and self._server.stdout is not None
        fd = self._server.stdout.fileno()
        while b"\n" not in self._inbox:
            left = deadline - time.monotonic()
            if left <= 0 or not select.select([fd], [], [], left)[0]:
                self.close()
                raise subprocess.TimeoutExpired("capability mcp", CLI_TIMEOUT_SECONDS)
            chunk = os.read(fd, 1 << 16)
            if not chunk:
                self.close()
                raise RuntimeError("capability mcp exited")
            self._inbox += chunk
        line, _, self._inbox = self._inbox.partition(b"\n")
        return line


def recent_sessions(shell: Shell, since: str) -> list[Session]:
    out = shell.run(
        ["cass", "sessions", "--since", since, "--limit", str(SWEEP_LIMIT), "--json"]
    )
    rows = json.loads(out).get("sessions", [])
    return [
        Session(r["path"], r.get("agent", ""), r.get("size_bytes", 0))
        for r in rows
        if r.get("path")
        and "/subagents/" not in r["path"]
        and r.get("human_turns", 1) > 0
    ]


def since_cutoff(since: str, now: float) -> float:
    """Epoch seconds for a cass-style relative window ("-2d", "-6h")."""
    match = RELATIVE_SINCE.fullmatch(since)
    if not match:
        raise ValueError(f"--since must look like -2d or -6h, got {since!r}")
    return now - int(match["count"]) * SINCE_UNIT_SECONDS[match["unit"]]


def recent_cursor_sessions(root: Path, cutoff: float) -> list[Session]:
    """Cursor agent transcripts cass does not index (its connector misses this layout)."""
    return [
        Session(str(f), "cursor", stat.st_size)
        for f in sorted(root.glob(CURSOR_TRANSCRIPT_GLOB))
        if (stat := f.stat()).st_mtime >= cutoff
    ]


def session_for_path(path: str) -> Session:
    agent = next(
        (agent for marker, agent in HARNESS_DIR_AGENT if marker in path), "claude_code"
    )
    return Session(path, agent, Path(path).stat().st_size if Path(path).exists() else 0)


def reader_ref(session: Session) -> str:
    """Grok sessions are indexed by updates.jsonl; the readable turns live beside it."""
    if session.agent == "grok":
        return str(Path(session.path).with_name("chat_history.jsonl"))
    return session.path


def conversation_ref(session: Session) -> str:
    """`<harness>:<id>` for get_recent_turns, the id read off the session's path."""
    harness = CAPABILITY_HARNESS.get(session.agent)
    if harness is None:
        raise RuntimeError(f"no transcript reader for agent {session.agent!r}")
    path = Path(session.path)
    if harness == "grok":  # <session id>/chat_history.jsonl or updates.jsonl
        return f"grok:{path.parent.name}"
    if harness == "codex":  # rollout-<time>-<session id>.jsonl
        rollout = CODEX_ROLLOUT_ID.fullmatch(path.name)
        if rollout is None:
            raise RuntimeError(f"not a codex rollout file: {session.path}")
        return f"codex:{rollout['id']}"
    return f"{harness}:{path.stem}"  # claude <id>.jsonl; cursor <id>/<id>.jsonl


def render_turns(recent: dict) -> str:
    """Plain `USER: ...` / `ASSISTANT: ...` text, oldest first, from get_recent_turns output."""
    return "".join(
        f"{label}: {message['content']}\n\n"
        for turn in recent["turns"]
        for message in turn["messages"]
        if (label := SPEAKER_LABEL.get(message["from"]))
    )


def transcript_text(shell: Shell, session: Session) -> str:
    recent = shell.capability(
        "run_get_recent_turns",
        {
            "conversation": conversation_ref(session),
            "turns": TURNS_ALL,
            "length_limit": MESSAGE_CHARS,
            "max_tokens": max(1, -(-MAX_TRANSCRIPT_CHARS // CHARS_PER_TOKEN)),
        },
    )
    return render_turns(recent)[-MAX_TRANSCRIPT_CHARS:]


def raw_session_text(session: Session) -> str:
    """Everything the session recorded, tool output included, with JSON escapes undone.

    The readable transcript drops tool output, but rule evidence usually quotes it
    (an error message, a test result), so evidence is checked against this instead.
    """
    paths = dict.fromkeys([Path(session.path), Path(reader_ref(session))])
    texts = []
    for path in paths:
        try:
            texts.append(path.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
    raw = "\n".join(texts)
    for escaped, plain in JSON_ESCAPES:
        raw = raw.replace(escaped, plain)
    return raw
