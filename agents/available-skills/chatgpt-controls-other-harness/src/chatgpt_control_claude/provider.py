"""Coding-harness dispatch. PROVIDER is required and names the CLI on PATH."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
from typing import Mapping, Sequence

from chatgpt_control_claude.grok import DEFAULT_MAX_TURNS, grok_command

SUPPORTED_PROVIDERS = ("grok", "claude")


def require_provider(env: Mapping[str, str] | None = None) -> str:
    value = (env if env is not None else os.environ).get("PROVIDER", "").strip()
    if not value:
        raise RuntimeError("PROVIDER is required, e.g. PROVIDER=grok")
    return value


def claude_command(
    *,
    prompt: str,
    cwd: Path,
    max_turns: int = DEFAULT_MAX_TURNS,
    extra_args: Sequence[str] = (),
) -> list[str]:
    if not prompt.strip():
        raise ValueError("prompt must not be empty")
    if max_turns <= 0:
        raise ValueError("max_turns must be positive")
    command = [
        "claude",
        "--print",
        "--output-format",
        "json",
        "--dangerously-skip-permissions",
        "--max-turns",
        str(max_turns),
    ]
    command.extend(extra_args)
    command.extend(["-p", prompt])
    return command


def harness_command(
    *,
    prompt: str,
    cwd: Path,
    env: Mapping[str, str] | None = None,
    extra_args: Sequence[str] = (),
) -> list[str]:
    provider = require_provider(env)
    if provider not in SUPPORTED_PROVIDERS:
        supported = ", ".join(SUPPORTED_PROVIDERS)
        raise RuntimeError(f"unknown PROVIDER {provider!r}; supported: {supported}")
    if shutil.which(provider) is None:
        raise RuntimeError(f"{provider} CLI is not on PATH")
    if provider == "grok":
        return grok_command(prompt=prompt, cwd=cwd, extra_args=extra_args)
    return claude_command(prompt=prompt, cwd=cwd, extra_args=extra_args)
