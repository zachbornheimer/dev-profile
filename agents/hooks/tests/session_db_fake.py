"""A stand-in ``psql`` for the omp session database, so no test reaches a real one.

``fake_session_db(tmp_path, sessions)`` returns the env a hook needs: ``PATH`` with a
fake ``psql`` first and a ``SESSIONS_DB_URL`` that wins over any real configuration.
The fake answers omp_session_store's two queries from ``sessions`` ({path: content})
and records each call in ``calls.log``.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

FAKE_PSQL = r"""#!/usr/bin/env python3
import json, os, sys
args = sys.argv[1:]
key = next(a.split("=", 1)[1] for a in args if a.startswith("key="))
sql = sys.stdin.read()
root = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(root, "calls.log"), "a") as log:
    log.write(json.dumps({"key": key, "host": os.environ.get("PGHOST"), "sql": sql.split()[1]}) + "\n")
if os.environ.get("PGHOST") == "unreachable":
    sys.exit(2)
sessions = json.load(open(os.path.join(root, "sessions.json")))
if sql.startswith("select path"):
    suffix = key.replace("\\_", "_").lstrip("%")
    hits = [p for p in sessions if p.endswith(suffix)]
    print(hits[0] if hits else "")
else:
    sys.stdout.write(sessions.get(key, ""))
"""


def fake_session_db(
    tmp_path: Path, sessions: dict[str, str], host: str = "db.test"
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
