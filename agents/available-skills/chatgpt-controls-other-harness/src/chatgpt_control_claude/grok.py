from __future__ import annotations

import json
import shutil
import subprocess
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

DEFAULT_TIMEOUT_SECONDS = 30 * 60
DEFAULT_MAX_TURNS = 64
DEFAULT_WORKER_RULES = (
    "You are a bounded implementation worker controlled by ChatGPT. "
    "Follow the requested architecture and scope exactly. Inspect repository instructions "
    "before editing. Do not broaden scope or substitute a different design. Do not commit, "
    "push, merge, reset, or clean unless the task explicitly authorizes it. Run the requested "
    "verification and report facts concisely."
)


@dataclass(frozen=True)
class GrokResult:
    """Result of one bounded Grok Build headless invocation."""

    argv: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str
    duration_seconds: float

    def json_output(self) -> object | None:
        """Parse Grok's final JSON object when available."""
        if not self.stdout.strip():
            return None
        try:
            return json.loads(self.stdout)
        except json.JSONDecodeError:
            return None


def grok_command(
    *,
    prompt: str,
    cwd: Path,
    max_turns: int = DEFAULT_MAX_TURNS,
    model: str | None = None,
    extra_args: Sequence[str] = (),
) -> list[str]:
    """Build the controlled Grok Build command used by generated runners.

    ChatGPT is the planner in this protocol. Grok runs as a fresh, bounded worker,
    so memory, Grok-side planning, and subagents are disabled by default.
    """
    if not prompt.strip():
        raise ValueError("prompt must not be empty")
    if max_turns <= 0:
        raise ValueError("max_turns must be positive")

    command = [
        "grok",
        "--no-auto-update",
        "--cwd",
        str(cwd),
        "--output-format",
        "json",
        "--always-approve",
        "--sandbox",
        "workspace",
        "--rules",
        DEFAULT_WORKER_RULES,
        "--no-memory",
        "--no-plan",
        "--no-subagents",
        "--disable-web-search",
        "--max-turns",
        str(max_turns),
    ]
    if model:
        command.extend(["--model", model])
    command.extend(extra_args)
    command.extend(["-p", prompt])
    return command


def run_grok(
    *,
    prompt: str,
    cwd: Path,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    max_turns: int = DEFAULT_MAX_TURNS,
    model: str | None = None,
    extra_args: Sequence[str] = (),
) -> GrokResult:
    """Run Grok Build once, synchronously, with a hard deadline."""
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    if shutil.which("grok") is None:
        raise RuntimeError("Grok Build CLI ('grok') is not on PATH")
    if not cwd.is_dir():
        raise FileNotFoundError(f"working directory does not exist: {cwd}")

    argv = grok_command(
        prompt=prompt,
        cwd=cwd,
        max_turns=max_turns,
        model=model,
        extra_args=extra_args,
    )

    started = time.monotonic()
    try:
        completed = subprocess.run(
            argv,
            cwd=str(cwd),
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError(f"Grok Build exceeded {timeout_seconds}s deadline") from exc

    return GrokResult(
        argv=tuple(argv),
        returncode=completed.returncode,
        stdout=completed.stdout or "",
        stderr=completed.stderr or "",
        duration_seconds=time.monotonic() - started,
    )
