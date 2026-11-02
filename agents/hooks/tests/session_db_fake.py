"""A stand-in ``psql`` for the omp session database, so no test reaches a real one.

``fake_session_db(tmp_path, sessions)`` returns the env a hook needs: ``PATH`` with a
fake ``psql`` first and a ``SESSIONS_DB_URL`` that wins over any real configuration.
The fake answers omp_session_store's two queries from ``sessions``: ``{path: content}``,
or ``{path: [content, mtime_ms]}`` when a test needs the row's age (a bare content row
is newer than any file). It applies TRANSCRIPT_SQL's rule in Python, and records each
call in ``calls.log`` with ``sent``: ``"full"``, ``"appended"``, or ``"nothing"``.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

FAKE_PSQL = r"""#!/usr/bin/env python3
import hashlib, json, os, sys
bound = dict(a.removeprefix("--set=").split("=", 1) for a in sys.argv[1:] if a.startswith("--set="))
key = bound["key"]
sql = sys.stdin.read()
root = os.path.dirname(os.path.abspath(__file__))


def record(sent):
    with open(os.path.join(root, "calls.log"), "a") as log:
        call = {"key": key, "host": os.environ.get("PGHOST"), "sql": sql.split()[1], "sent": sent}
        log.write(json.dumps(call) + "\n")


if os.environ.get("PGHOST") == "unreachable":
    record("nothing")
    sys.exit(2)
sessions = json.load(open(os.path.join(root, "sessions.json")))
if sql.startswith("select path"):
    record("nothing")
    suffix = key.replace("\\_", "_").lstrip("%")
    hits = [p for p in sessions if p.endswith(suffix)]
    print(hits[0] if hits else "")
    sys.exit(0)
row = sessions.get(key)
if row is None:
    record("nothing")
    sys.exit(0)
content, mtime_ms = (row, 4102444800000) if isinstance(row, str) else row
held = int(bound["length"])
held_tail = content[max(0, held - 4096):held].encode()
if mtime_ms <= int(bound["since"]):
    sent, body = "nothing", ""
elif len(content) > held >= 0 and hashlib.sha256(held_tail).hexdigest() == bound["tail_hash"]:
    sent, body = "appended", "+" + content[held:]
else:
    sent, body = "full", "=" + content
record(sent)
print(f"{mtime_ms}\n{len(content)}\n{body}")
"""


def fake_session_db(
    tmp_path: Path, sessions: dict[str, str | list], host: str = "db.test"
) -> dict[str, str]:
    bin_dir = tmp_path / "fake-psql-bin"
    bin_dir.mkdir(exist_ok=True)
    (bin_dir / "sessions.json").write_text(json.dumps(sessions))
    psql = bin_dir / "psql"
    psql.write_text(FAKE_PSQL)
    psql.chmod(0o755)
    return {
        "PATH": f"{bin_dir}:{os.environ.get('PATH', '')}",
        "SESSIONS_DB_URL": f"postgresql://user:secret@{host}/sessions?sslmode=require",
    }


def fake_calls(tmp_path: Path) -> list[dict]:
    log = tmp_path / "fake-psql-bin" / "calls.log"
    return (
        [json.loads(line) for line in log.read_text().splitlines()]
        if log.exists()
        else []
    )
