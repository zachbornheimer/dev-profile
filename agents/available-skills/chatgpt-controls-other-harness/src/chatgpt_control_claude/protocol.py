from __future__ import annotations

import re
import uuid

_RUNNER_RE = re.compile(
    r"^run-([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\.py$",
    re.IGNORECASE,
)


def new_run_id() -> str:
    return str(uuid.uuid4())


def runner_filename(run_id: str) -> str:
    uuid.UUID(run_id)
    return f"run-{run_id}.py"


def evidence_zip_filename(run_id: str) -> str:
    uuid.UUID(run_id)
    return f"{run_id}.zip"


def parse_runner_id(filename: str) -> str:
    match = _RUNNER_RE.match(filename)
    if not match:
        raise ValueError(f"not a runner filename: {filename!r}")
    value = match.group(1).lower()
    uuid.UUID(value)
    return value
