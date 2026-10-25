"""Beads workspace facade for ensure-beads: find one, or start creating one.

Owns the two beads/process boundaries the hook needs (``bd where`` and a
detached ``bd init``) plus the init lock, so a test substitutes a fake
``bd`` on PATH and never touches Dolt.
"""

from __future__ import annotations

import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

BD_PROGRAM = "bd"
LOCATE_TIMEOUT_SECS = 15
LOCK_NAME = "ensure-beads.lock"
LOCK_STALE_SECS = 300
# Local, never-committed, no instruction files, no git hooks, no role prompt;
# --init-if-missing makes a lost race a clean no-op instead of an error.
INIT_ARGS = (
    "init",
    "--quiet",
    "--stealth",
    "--skip-agents",
    "--skip-hooks",
    "--role",
    "maintainer",
    "--init-if-missing",
)
# Run bd, then always release the lock (first arg), whatever bd's status.
RUN_THEN_UNLOCK = 'lock=$1; shift; "$@"; rm -f "$lock"'


@dataclass(frozen=True, slots=True)
class BeadsWorkspace:
    """The beads workspace a repo's sessions share (worktrees resolve to the main checkout's)."""

    repo_root: Path
    lock_dir: Path

    def exists_for(self, directory: Path) -> bool:
        """True when ``bd where`` resolves a workspace from ``directory`` (honours BEADS_DIR)."""
        try:
            done = subprocess.run(
                [BD_PROGRAM, "where"],
                cwd=directory,
                capture_output=True,
                text=True,
                timeout=LOCATE_TIMEOUT_SECS,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return True  # cannot tell: do nothing rather than risk a second init
        return done.returncode == 0

    def start_init_in_background(self) -> bool:
        """Detach ``bd init`` at the repo root; False if another init holds the lock."""
        lock = self.lock_dir / LOCK_NAME
        if not self._take_lock(lock):
            return False
        try:
            subprocess.Popen(
                ["sh", "-c", RUN_THEN_UNLOCK, "sh", str(lock), BD_PROGRAM, *INIT_ARGS],
                cwd=self.repo_root,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError:
            lock.unlink(missing_ok=True)
            return False
        return True

    @staticmethod
    def _take_lock(lock: Path) -> bool:
        """Create the lock exclusively; steal it only when older than LOCK_STALE_SECS."""
        for _ in range(2):
            try:
                os.close(os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
                return True
            except FileExistsError:
                try:
                    age = time.time() - lock.stat().st_mtime
                except FileNotFoundError:
                    continue
                if age < LOCK_STALE_SECS:
                    return False
                lock.unlink(missing_ok=True)
        return False
