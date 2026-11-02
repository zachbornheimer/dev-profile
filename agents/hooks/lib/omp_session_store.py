"""omp transcripts that live in the session database instead of on disk.

omp with ``SESSIONS_DB_URL`` set writes each session to the ``omp_session_files``
table (``path``, ``content``) and leaves no file at the ``transcript_path`` it
reports. Hooks that read transcripts call ``readable_transcript(path)``: it
returns the file when it exists, else a private copy fetched from the database
into the hook state dir, else ``None``. Every failure (no URL, no ``psql``, a
timeout, no row) is ``None``, so callers keep their fail-open behavior.

A copy holds the session's first 64 KiB (omp's header rows, which decide the
format) and its last 8 MB; a longer session is joined at a line that will not
decode, which every reader already skips.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from hook_common.settings import HookSettings

# Both queries are fixed text; the only input, the session key, is bound by psql as the quoted literal :'key'.
TRANSCRIPT_SQL = (
    "select case when length(content) <= 8065536 then content "
    "else left(content, 65536) || E'\\n' || right(content, 8000000) end "
    "from omp_session_files where path = :'key';\n"
)
SESSION_PATH_SQL = "select path from omp_session_files where path like :'key' order by mtime_ms desc limit 1;\n"
QUERY_TIMEOUT_SECS = 6.0
CACHE_DIR = "omp-session-store"
URL_FILE = Path.home() / ".config" / "dev-env" / "runtime" / "omp-session-db-url"
OMP_ENV_FILE = Path.home() / ".omp" / ".env"
POSTGRES_URL = re.compile(r"postgres(?:ql)?://[^\s'\"]+")
SESSION_ID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
OMP_SESSION_FILE = re.compile(rf"_({SESSION_ID.pattern})\.jsonl$")


def readable_transcript(path: str | Path | None) -> Path | None:
    """A file holding the transcript at ``path``: the file itself, or a copy from the session database."""
    if not path:
        return None
    transcript = Path(path).expanduser()
    if transcript.is_file():
        return transcript
    found = OMP_SESSION_FILE.search(transcript.name)
    if not found:
        return None
    content = _query(TRANSCRIPT_SQL, str(transcript))
    return _cache(found.group(1), content) if content else None


def stored_session_path(session_id: str) -> str | None:
    """The ``transcript_path`` omp recorded for ``session_id``, when the database holds that session."""
    if not SESSION_ID.fullmatch(session_id):
        return None
    return _query(SESSION_PATH_SQL, f"%\\_{session_id}.jsonl").strip() or None


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


def _query(sql: str, key: str) -> str:
    """psql's single-value output for ``sql`` with ``key`` bound; "" on any failure."""
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
                "--set",
                "ON_ERROR_STOP=1",
                "--set",
                f"key={key}",
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


def _cache(session_id: str, content: str) -> Path | None:
    directory = HookSettings.from_env().state_dir / CACHE_DIR
    target = directory / f"{session_id}.jsonl"
    temporary = directory / f".{session_id}.{os.getpid()}.tmp"
    try:
        directory.mkdir(parents=True, exist_ok=True)
        temporary.write_text(content.removesuffix("\n") + "\n")
        temporary.chmod(0o600)
        temporary.replace(target)
    except OSError:
        temporary.unlink(missing_ok=True)
        return None
    return target
