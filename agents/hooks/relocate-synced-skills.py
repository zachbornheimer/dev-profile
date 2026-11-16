#!/usr/bin/env python3
"""SessionStart — move synced skills into the picker-only available-skills tree.

Merge ~/.agents/skills/synced into ~/.agents/available-skills/synced and remove
only the source tree. Fail open. Prints nothing.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

HOME_ENV = "SYNCED_RELOCATE_HOME"
AGENTS_SYNCED = Path(".agents") / "skills" / "synced"
AVAILABLE_SYNCED = Path(".agents") / "available-skills" / "synced"


def home_dir() -> Path:
    raw = os.environ.get(HOME_ENV, "").strip()
    if raw:
        return Path(raw)
    return Path.home()


def relocate(source: Path, dest: Path) -> None:
    if not source.exists() or not source.is_dir():
        return
    try:
        if source.resolve() == dest.resolve():
            return
    except OSError:
        return
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, dest, dirs_exist_ok=True, symlinks=True)
    shutil.rmtree(source)


def drain_stdin() -> None:
    try:
        sys.stdin.read()
    except OSError:
        return


def main() -> int:
    try:
        drain_stdin()
        home = home_dir()
        dest = home / AVAILABLE_SYNCED
        relocate(home / AGENTS_SYNCED, dest)
    except (OSError, shutil.Error):
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
