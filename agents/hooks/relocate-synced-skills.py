#!/usr/bin/env python3
"""SessionStart — move plugin `synced/` trees out of harness auto-scan dirs.

Claude and Grok dump every SKILL.md under `skills/`. Plugin sync writes
`synced/` there. Merge those trees into `~/.agents/available-skills/synced`
(picker-only) and delete the auto-scan copy. Also drop leftover Claude skill
dirs (`.trash`, plugin dumps) so OpenCode cannot auto-discover them. The
harness skills dir stays empty; skills are picker-only. Fail open. Prints nothing.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

HOME_ENV = "SYNCED_RELOCATE_HOME"
AGENTS_SYNCED = Path(".agents") / "skills" / "synced"
CLAUDE_SKILLS = Path(".claude") / "skills"
CLAUDE_SYNCED = CLAUDE_SKILLS / "synced"
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


def remove_path(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
        return
    if path.is_dir():
        shutil.rmtree(path)


def sweep_claude_skills(skills_dir: Path) -> None:
    if not skills_dir.exists() or not skills_dir.is_dir():
        return
    for child in list(skills_dir.iterdir()):
        remove_path(child)


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
        relocate(home / CLAUDE_SYNCED, dest)
        sweep_claude_skills(home / CLAUDE_SKILLS)
    except (OSError, shutil.Error):
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
