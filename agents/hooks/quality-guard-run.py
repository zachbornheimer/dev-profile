#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""PATH-safe quality-guard launcher for Claude Code, Grok, and Cursor hooks.

Usage: quality-guard-run.py --mode=fast|pretool-review

Under Grok, Claude's settings.json hooks are also loaded (compat.claude.hooks).
To avoid running quality-guard twice, Grok-native hooks set:
  QUALITY_GUARD_SOURCE=grok-native
When GROK_SESSION_ID is set and that flag is absent, this allows and exits
(the native Grok hook will run the real check).
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))

from hook_common import run_fail_open

HOOK_NAME = "quality-guard-run"

GROK_DEFERRED_DECISION = (
    '{"decision":"allow","reason":"quality-guard deferred to grok-native hook"}'
)
BINARY_NOT_FOUND_DECISION = '{"decision":"allow","reason":"quality-guard binary not found on PATH"}'
GROK_NATIVE_SOURCE = "grok-native"
QUALITY_GUARD_BINARY_NAME = "quality-guard"
EXTRA_PATH_DIRS = ("/opt/homebrew/bin", "/usr/local/bin")
GO_BIN_RELATIVE = "go/bin"
DEFAULT_LOG_LEVEL = "debug"
DEFAULT_LOG_FILE = "/tmp/qg-pretool.log"


def _search_path(env: dict[str, str]) -> str:
    go_bin = os.path.join(env.get("HOME", ""), GO_BIN_RELATIVE)
    return os.pathsep.join([go_bin, *EXTRA_PATH_DIRS, env.get("PATH", "")])


def find_quality_guard_binary(env: dict[str, str]) -> str | None:
    """PATH lookup with the same fallback the .sh used: explicit ~/go/bin check."""
    found = shutil.which(QUALITY_GUARD_BINARY_NAME, path=_search_path(env))
    if found:
        return found
    go_bin_binary = os.path.join(env.get("HOME", ""), GO_BIN_RELATIVE, QUALITY_GUARD_BINARY_NAME)
    if os.access(go_bin_binary, os.X_OK):
        return go_bin_binary
    return None


def _is_grok_dual_load(env: dict[str, str]) -> bool:
    return (
        bool(env.get("GROK_SESSION_ID")) and env.get("QUALITY_GUARD_SOURCE") != GROK_NATIVE_SOURCE
    )


def main(argv: list[str], env: dict[str, str]) -> int:
    if _is_grok_dual_load(env):
        print(GROK_DEFERRED_DECISION)
        return 0

    binary = find_quality_guard_binary(env)
    if binary is None:
        print(BINARY_NOT_FOUND_DECISION)
        return 0

    run_env = dict(env)
    run_env["PATH"] = _search_path(env)
    run_env.setdefault("QUALITY_GUARD_LOG_LEVEL", DEFAULT_LOG_LEVEL)
    run_env.setdefault("QUALITY_GUARD_LOG_FILE", DEFAULT_LOG_FILE)
    os.execve(binary, [binary, *argv], run_env)
    return 1  # unreachable: execve replaces this process on success


if __name__ == "__main__":
    run_fail_open(HOOK_NAME, lambda: main(sys.argv[1:], dict(os.environ)))
