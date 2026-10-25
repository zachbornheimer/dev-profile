"""The one seam every hook uses to run ``git -C <dir> ...``.

Hook-specific facades (worktree provisioning, cleanup, orchestrator-only
probes) put domain verbs on top of this; none of them spawns git itself.
A test substitutes a fake ``Git`` instead of a real repository.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import NamedTuple

GIT_NOT_RUNNABLE_STATUS = 127


class GitResult(NamedTuple):
    """Exit status and stdout; unpacks as ``(exit_code, stdout)``."""

    exit_code: int
    stdout: str

    @property
    def ok(self) -> bool:
        return self.exit_code == 0

    @property
    def text(self) -> str:
        """Stripped stdout on success, "" on failure — the usual one-line read."""
        return self.stdout.strip() if self.ok else ""


@dataclass(frozen=True, slots=True)
class Git:
    """Runs git against a directory. A missing binary or a timeout reads as a failed run."""

    def run(self, directory: str, *args: str, timeout: float | None = None) -> GitResult:
        try:
            done = subprocess.run(
                ["git", "-C", directory, *args],
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return GitResult(GIT_NOT_RUNNABLE_STATUS, "")
        return GitResult(done.returncode, done.stdout)


GIT = Git()
