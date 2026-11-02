"""The freshest copy of an omp transcript, on disk or in the session database.

omp with ``SESSIONS_DB_URL`` set writes each session to the ``omp_session_files``
table (``path``, ``content``, ``mtime_ms``) and nothing to the ``transcript_path``
it reports. That path may hold no file, or a file an earlier run left behind,
which stops at whatever was asked then. Hooks that read transcripts call
``readable_transcript(path)``: it returns the newest local copy (that file, or the
copy kept in the hook state dir), brought up to date from the database when the
database's row is newer. Every database failure (no URL, no ``psql``, a timeout,
no row) leaves the local copy, else ``None``, so callers keep their fail-open
behavior.

The scope guard reads the transcript on every tool call, so one query does all
of it and sends only what the copy lacks. omp appends to a session, so a grown
row whose text at the copy's length still ends the way the copy ends sends just
the appended text; anything else sends the row whole. A whole copy holds the
session's first 64 KiB (omp's header rows, which decide the format) and its last
8 MB; a longer session is joined at a line that will not decode, which every
reader already skips.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from hook_common.settings import HookSettings

# Both queries are fixed text; their inputs are bound by psql as quoted literals (:'key', ...).
# TRANSCRIPT_SQL answers three lines: the row's mtime_ms, its length in characters, then
#   ""             the row is no newer than :'since' (the newest local copy);
#   "+<appended>"  the row grew past :'length' and its text up to there ends in the
#                  TAIL_CHARS whose sha256 is :'tail_hash' (the end of the copy);
#   "=<content>"   otherwise: the whole row, capped as the module docstring says.
TRANSCRIPT_SQL = (
    "select mtime_ms || E'\\n' || length(content) || E'\\n' || case "
    "when mtime_ms <= :'since'::bigint then '' "
    "when length(content) > :'length'::int and encode(sha256(convert_to("
    "substr(content, :'length'::int - 4095, 4096), 'UTF8')), 'hex') = :'tail_hash' "
    "then '+' || substr(content, :'length'::int + 1) "
    "when length(content) <= 8065536 then '=' || content "
    "else '=' || left(content, 65536) || E'\\n' || right(content, 8000000) end "
    "from omp_session_files where path = :'key';\n"
)
TAIL_CHARS = 4096  # the 4096 in TRANSCRIPT_SQL
SESSION_PATH_SQL = "select path from omp_session_files where path like :'key' order by mtime_ms desc limit 1;\n"
QUERY_TIMEOUT_SECS = 6.0
CACHE_DIR = "omp-session-store"
URL_FILE = Path.home() / ".config" / "dev-env" / "runtime" / "omp-session-db-url"
OMP_ENV_FILE = Path.home() / ".omp" / ".env"
POSTGRES_URL = re.compile(r"postgres(?:ql)?://[^\s'\"]+")
SESSION_ID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
OMP_SESSION_FILE = re.compile(rf"_({SESSION_ID.pattern})\.jsonl$")


def readable_transcript(path: str | Path | None) -> Path | None:
    """The freshest file holding the transcript at ``path``; ``None`` when there is none."""
    if not path:
        return None
    transcript = Path(path).expanduser()
    found = OMP_SESSION_FILE.search(transcript.name)
    if not found:
        return transcript if transcript.is_file() else None
    session_id = found.group(1)
    copy = Copy.load(session_id)
    local = max(
        (file for file in (transcript, copy and copy.path) if file and file.is_file()),
        key=_mtime_ms,
        default=None,
    )
    reply = _query(
        TRANSCRIPT_SQL,
        key=str(transcript),
        since=str(_mtime_ms(local) if local else -1),
        length=str(copy.length if copy else -1),
        tail_hash=copy.tail_hash() if copy else "",
    )
    mtime_ms, _, rest = reply.partition("\n")
    length, _, body = rest.partition("\n")
    body = body.removesuffix("\n")  # psql ends its output with a newline of its own
    if not (mtime_ms.isdigit() and length.isdigit()) or body[:1] not in ("+", "="):
        return local
    base = copy.path if body[0] == "+" and copy else None
    written = Copy.write(session_id, body[1:], int(mtime_ms), int(length), base)
    return written or local


def stored_session_path(session_id: str) -> str | None:
    """The ``transcript_path`` omp recorded for ``session_id``, when the database holds that session."""
    if not SESSION_ID.fullmatch(session_id):
        return None
    return _query(SESSION_PATH_SQL, key=f"%\\_{session_id}.jsonl").strip() or None


def database_url() -> str:
    """``SESSIONS_DB_URL`` from the environment, omp's ``~/.omp/.env``, or dev-env's runtime file; "" if none is a Postgres URL."""
    candidates = [os.environ.get("SESSIONS_DB_URL", "")]
    for source in (OMP_ENV_FILE, URL_FILE):
        try:
            candidates.append(source.read_text())
        except OSError:
            continue
    for text in candidates:
        found = POSTGRES_URL.search(text)
        if found:
            return found.group(0)
    return ""


def connection_env(url: str) -> dict[str, str]:
    """libpq's PG* variables for a ``postgres://`` URL; psql reads them, so the URL never reaches argv."""
    parts = urlsplit(url)
    query = {key: values[-1] for key, values in parse_qs(parts.query).items()}
    env = {
        "PGHOST": parts.hostname or "",
        "PGPORT": str(parts.port or ""),
        "PGUSER": unquote(parts.username or ""),
        "PGPASSWORD": unquote(parts.password or ""),
        "PGDATABASE": unquote(parts.path.lstrip("/")),
        "PGSSLMODE": query.get("sslmode", ""),
        "PGCHANNELBINDING": query.get("channel_binding", ""),
    }
    return {key: value for key, value in env.items() if value}


def _query(sql: str, **bound: str) -> str:
    """psql's single-value output for ``sql`` with each of ``bound`` set as a psql variable; "" on any failure."""
    url = database_url()
    if not url:
        return ""
    try:
        # Argument list, no shell; the connection comes from libpq's environment variables.
        done = subprocess.run(
            [
                "/usr/bin/env",
                "psql",
                "--no-psqlrc",
                "--tuples-only",
                "--no-align",
                "--quiet",
                *(
                    f"--set={name}={value}"
                    for name, value in {"ON_ERROR_STOP": "1", **bound}.items()
                ),
            ],
            input=sql,
            env={**os.environ, **connection_env(url)},
            capture_output=True,
            text=True,
            timeout=QUERY_TIMEOUT_SECS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return done.stdout if done.returncode == 0 else ""


@dataclass(frozen=True)
class Copy:
    """The database's copy of one session in the hook state dir, and how many of the row's characters it holds.

    A record beside the copy holds the row's ``mtime_ms`` and length; the copy's own
    mtime is set to the same ``mtime_ms``. The record is written first, so a reader
    that lands between the two writes finds them disagreeing and fetches whole.
    """

    path: Path
    length: int

    @classmethod
    def load(cls, session_id: str) -> Copy | None:
        path = _cache_path(session_id)
        try:
            record = json.loads(path.with_suffix(".json").read_text())
            if path.is_file() and record["mtime_ms"] == _mtime_ms(path):
                return cls(path, int(record["length"]))
        except (OSError, ValueError, KeyError, TypeError):
            pass
        return None

    def tail_hash(self) -> str:
        """sha256 of the copy's last TAIL_CHARS characters, as TRANSCRIPT_SQL hashes the row's."""
        try:
            with self.path.open("rb") as handle:
                size = handle.seek(0, os.SEEK_END)
                handle.seek(max(0, size - 4 * TAIL_CHARS - 4))
                tail = handle.read().decode("utf-8", errors="ignore")[-TAIL_CHARS:]
        except OSError:
            return ""
        return hashlib.sha256(tail.encode()).hexdigest()

    @staticmethod
    def write(
        session_id: str, text: str, mtime_ms: int, length: int, base: Path | None
    ) -> Path | None:
        """``base`` plus ``text`` (or ``text`` alone) as the session's copy; ``None`` when it cannot be written."""
        target = _cache_path(session_id)
        temporary = target.with_name(f".{session_id}.{os.getpid()}.tmp")
        record = target.with_name(f".{session_id}.{os.getpid()}.json.tmp")
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            if base:
                shutil.copyfile(base, temporary)
            with temporary.open(
                "a" if base else "w", encoding="utf-8", newline=""
            ) as handle:
                handle.write(text)
            temporary.chmod(0o600)
            os.utime(temporary, ns=(mtime_ms * 1_000_000, mtime_ms * 1_000_000))
            record.write_text(json.dumps({"mtime_ms": mtime_ms, "length": length}))
            record.replace(target.with_suffix(".json"))
            temporary.replace(target)
        except OSError:
            temporary.unlink(missing_ok=True)
            record.unlink(missing_ok=True)
            return None
        return target


def _cache_path(session_id: str) -> Path:
    return HookSettings.from_env().state_dir / CACHE_DIR / f"{session_id}.jsonl"


def _mtime_ms(path: Path) -> int:
    return path.stat().st_mtime_ns // 1_000_000
