"""Drift-report parsing and chezmoi-apply detection for chezmoi-guard.

Port of chezmoi-guard.sh's guard_drift_report / guard_live_ahead_paths /
command_is_chezmoi_apply.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

LIVE_AHEAD_SECTION_PREFIX = "== live-ahead"
SECTION_MARKER_PREFIX = "== "
RE_ADD_HINT = "Run chezmoi re-add <path> before chezmoi apply."
DRIFT_REPORT_TIMEOUT_SECS = 30
DRIFT_REPORT_FILE_OVERRIDE_ENV = "CHEZMOI_DRIFT_REPORT_FILE"

ProcessRunner = Callable[[list[str]], subprocess.CompletedProcess[str]]


def _run_process(argv: list[str]) -> subprocess.CompletedProcess[str]:
    """The real process boundary — the only place this module shells out."""
    return subprocess.run(
        argv, capture_output=True, text=True, timeout=DRIFT_REPORT_TIMEOUT_SECS, check=False
    )


@dataclass(frozen=True, slots=True)
class DriftReportSource:
    """Facade over chezmoi-drift.sh --report: a fixture file in tests, the real script otherwise.

    ``env`` and ``run_process`` are injected (defaulting to the process
    environment and a real subprocess call) so a test can substitute a
    fixture report or a fake process without a real chezmoi tree.
    """

    hooks_dir: Path
    env: Mapping[str, str] = field(default_factory=lambda: os.environ)
    run_process: ProcessRunner = _run_process

    def read(self) -> str:
        override = self.env.get(DRIFT_REPORT_FILE_OVERRIDE_ENV)
        if override:
            return Path(override).read_text()
        binary = self.hooks_dir / "bin" / "chezmoi-drift.sh"
        result = self.run_process([str(binary), "--report"])
        if result.returncode != 0:
            raise RuntimeError(f"chezmoi-drift.sh --report failed: {result.stderr}")
        return result.stdout


def live_ahead_paths(report: str) -> list[str]:
    """Live paths classified live-ahead — the dangerous apply direction."""
    paths: list[str] = []
    in_live_section = False
    for line in report.split("\n"):
        if line.startswith(LIVE_AHEAD_SECTION_PREFIX):
            in_live_section = True
            continue
        if line.startswith(SECTION_MARKER_PREFIX):
            in_live_section = False
            continue
        if in_live_section:
            stripped = line.lstrip()
            if stripped:
                paths.append(stripped)
    return paths


def refuse_message(paths: list[str]) -> str:
    lines = [
        "chezmoi-guard: refuse apply: live is ahead of source (unlanded edit would be reverted):"
    ]
    lines.extend(f"  {path}" for path in paths)
    lines.append(RE_ADD_HINT)
    return "\n".join(lines)


_CONTROL_OPERATORS = frozenset({"&&", ";", "|", "||"})


def command_is_chezmoi_apply(words: list[str]) -> bool:
    """Token-exact ``chezmoi apply``, resetting at each unquoted compound-command operator."""
    in_chezmoi = has_apply = False
    for word in words:
        if word in _CONTROL_OPERATORS:
            if in_chezmoi and has_apply:
                return True
            in_chezmoi = has_apply = False
            continue
        if word == "chezmoi":
            in_chezmoi = True
        if in_chezmoi and word == "apply":
            has_apply = True
    return in_chezmoi and has_apply


def print_to_stderr(text: str) -> None:
    print(text, file=sys.stderr)
