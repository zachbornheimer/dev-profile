"""Choose a ChatGPT Files-in-chat runner row.

The Accessibility list is document-ordered top to bottom. Recycled ghost rows
pile on one y. Newest files currently sit at the bottom; FILES_LIST_NEWEST
flips that without touching AX.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Callable, Iterable, Mapping

RUN_ARTIFACT_RE = re.compile(
    r"^run-([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\.[^./]+$",
    re.IGNORECASE,
)
RUN_PY_RE = re.compile(
    r"^run-([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\.py$",
    re.IGNORECASE,
)
RUN_EXECUTE_RE = re.compile(
    r"^run-([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\.(py|zip)$",
    re.IGNORECASE,
)

# ChatGPT currently paints newest files at the bottom of Files in chat.
FILES_LIST_NEWEST = "bottom"
MIN_ROW_GAP = 20.0
RECYCLE_Y_EPSILON = 2.0


@dataclass(frozen=True, slots=True)
class FileRow:
    name: str
    y: float
    x: float = 0.0


def artifact_uuid(filename: str) -> str | None:
    match = RUN_ARTIFACT_RE.match(filename)
    if not match:
        return None
    return match.group(1).lower()


def is_executable_runner(filename: str) -> bool:
    uid = artifact_uuid(filename)
    if uid is None:
        return False
    return Path(filename).suffix.lower() in {".py", ".zip"}


def runner_argv(uv: str, runner: Path) -> list[str]:
    """Zipapp: `uv run python <zip>`. Script: `uv run -- <py>`."""
    if runner.suffix.lower() == ".zip":
        return [uv, "run", "python", str(runner)]
    return [uv, "run", "--", str(runner)]


def visible_rows(rows: Iterable[FileRow]) -> list[FileRow]:
    """Keep the on-screen list; drop the same-y Accessibility recycle pile."""
    material = list(rows)
    stacked = {
        round(row.y)
        for row in material
        if sum(1 for other in material if abs(other.y - row.y) < RECYCLE_Y_EPSILON) >= 3
    }
    visible: list[FileRow] = []
    last_y: float | None = None
    for row in material:
        if round(row.y) in stacked:
            continue
        if last_y is not None and row.y + RECYCLE_Y_EPSILON < last_y:
            continue
        if last_y is not None and abs(row.y - last_y) < MIN_ROW_GAP:
            continue
        visible.append(row)
        last_y = row.y
    return visible


def pick_runner(
    rows: Iterable[FileRow],
    *,
    processed: Mapping[str, object],
    downloads: Path,
    newest: str = FILES_LIST_NEWEST,
    exists: Callable[[Path], bool] | None = None,
) -> FileRow | None:
    """First unmatched run-<uuid>.* from the newest end of the visible list."""
    visible = visible_rows(rows)
    ordered = list(reversed(visible)) if newest == "bottom" else list(visible)
    seen: set[str] = set()
    for row in ordered:
        if row.name in seen:
            continue
        seen.add(row.name)
        uid = artifact_uuid(row.name)
        if uid is None:
            continue
        # Only the newest run-* in the Files list. Never walk back to leftovers.
        if uid in processed:
            return None
        return row
    return None
