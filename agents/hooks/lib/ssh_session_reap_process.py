"""Facade over reading the process table and signalling a pid.

Both sides have a test seam (SSH_REAP_PS_FILE, SSH_REAP_KILL_FILE) so a test
never needs a live process table or to actually signal anything.
"""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess
from dataclasses import dataclass

PS_TIMEOUT_SECS_DEFAULT = 3.0


@dataclass(frozen=True, slots=True)
class ProcessTable:
    ps_file: str | None
    ps_timeout_secs: float = PS_TIMEOUT_SECS_DEFAULT

    def read(self) -> str:
        if self.ps_file:
            try:
                return open(self.ps_file, encoding="utf-8").read()
            except OSError:
                return ""
        try:
            result = subprocess.run(
                ["ps", "eww", "-ax", "-o", "pid=,ppid=,command="],
                capture_output=True,
                text=True,
                timeout=self.ps_timeout_secs,
                check=False,
            )
        except (subprocess.TimeoutExpired, OSError):
            return ""
        return result.stdout if result.returncode == 0 else ""


@dataclass(frozen=True, slots=True)
class ProcessKiller:
    kill_file: str | None

    def terminate(self, pid: int) -> None:
        if self.kill_file:
            with open(self.kill_file, "a", encoding="utf-8") as handle:
                handle.write(f"TERM {pid}\n")
            return
        with contextlib.suppress(OSError):
            os.kill(pid, signal.SIGTERM)
