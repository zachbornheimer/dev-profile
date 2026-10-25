"""Facade over lib/work-order-compile.py, run as a subprocess.

The compiler ships its own ``uv run --script`` dependencies (jsonschema,
pyyaml, jsonpatch), so the stdlib-only gate calls it exactly as
work-order-gate.sh does rather than importing it.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

COMPILE_TIMEOUT_SECS = 20
COMPILE_SCRIPT_ENV = "WORK_ORDER_GATE_COMPILE_SCRIPT"  # test seam; unset in production
DEFAULT_COMPILE_SCRIPT = Path(__file__).resolve().parent / "work-order-compile.py"


def compile_envelope(fields: Mapping[str, Any]) -> str:
    """The compiler's stdin, and the worktree target record: ``jq -c`` formatted."""
    return json.dumps(dict(fields), separators=(",", ":"), ensure_ascii=False)


@dataclass(frozen=True, slots=True)
class WorkOrderCompiler:
    script: Path

    @classmethod
    def from_env(cls, env: Mapping[str, str] = os.environ) -> WorkOrderCompiler:
        override = env.get(COMPILE_SCRIPT_ENV)
        return cls(Path(override) if override else DEFAULT_COMPILE_SCRIPT)

    def is_runnable(self) -> bool:
        return shutil.which("uv") is not None and os.access(self.script, os.X_OK)

    def compile(self, envelope: str) -> dict[str, Any] | None:
        """The compiler's verdict, or None for any failure — the gate fails open on None."""
        try:
            done = subprocess.run(
                [str(self.script), "compile"],
                input=envelope,
                capture_output=True,
                text=True,
                timeout=COMPILE_TIMEOUT_SECS,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        if done.returncode != 0 or not done.stdout.strip():
            return None
        try:
            verdict = json.loads(done.stdout)
        except ValueError:
            return None
        return verdict if isinstance(verdict, dict) else None
