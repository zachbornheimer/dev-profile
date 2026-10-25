"""wt (worktrunk) adapter: create or reuse one worktree at an exact dest."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass

WT_BIN_ENV = "WORKTREE_PROVISION_WT"
ALREADY_EXISTS_HINT = "already exists"
SWITCH_TIMEOUT_SECS = 120.0


class WorktrunkError(Exception):
    """wt switch failed in a way this hook cannot recover from."""


@dataclass(frozen=True, slots=True)
class SwitchResult:
    path: str
    branch: str
    created: bool


def resolve_wt_bin(env: Mapping[str, str] = os.environ) -> str:
    """WORKTREE_PROVISION_WT is a test seam: set (even empty) means use that value."""
    if WT_BIN_ENV in env:
        return env[WT_BIN_ENV]
    return shutil.which("wt") or ""


def parse_switch_json(stdout: str) -> dict[str, object]:
    """First JSON object on stdout. wt --format=json still prints a human line after it."""
    for line in stdout.splitlines():
        stripped = line.strip()
        if stripped.startswith("{"):
            payload = json.loads(stripped)
            if isinstance(payload, dict):
                return payload
    raise WorktrunkError("wt switch --format=json printed no JSON object")


def worktree_path_toml(dest: str) -> str:
    escaped = dest.replace("\\", "\\\\").replace('"', '\\"')
    return f'worktree-path = "{escaped}"'


def _switch_argv(
    wt_bin: str,
    repo_root: str,
    branch: str,
    dest: str,
    *,
    create: bool,
    base: str | None,
) -> list[str]:
    argv = [
        wt_bin,
        "-C",
        repo_root,
        "--config-set",
        worktree_path_toml(dest),
        "switch",
    ]
    if create:
        argv.append("--create")
    argv.extend([branch, "--no-cd", "--format=json", "-y", "--no-hooks"])
    if create:
        argv.append("--clobber")
        if base:
            argv.extend(["--base", base])
    return argv


def switch_worktree(
    wt_bin: str,
    repo_root: str,
    branch: str,
    dest: str,
    *,
    create: bool,
    base: str | None = None,
    timeout_secs: float = SWITCH_TIMEOUT_SECS,
) -> SwitchResult:
    """One wt switch. Raises WorktrunkError on failure."""
    argv = _switch_argv(wt_bin, repo_root, branch, dest, create=create, base=base)
    try:
        done = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout_secs,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise WorktrunkError(f"wt switch failed for {branch}: {exc}") from exc
    if done.returncode != 0:
        detail = (done.stderr or done.stdout).strip() or f"exit {done.returncode}"
        raise WorktrunkError(detail)
    payload = parse_switch_json(done.stdout)
    path = payload.get("path")
    named = payload.get("branch")
    if not isinstance(path, str) or not path:
        raise WorktrunkError(f"wt switch JSON missing path: {payload}")
    return SwitchResult(
        path=path,
        branch=named if isinstance(named, str) else branch,
        created=create and payload.get("action") == "created",
    )


def ensure_worktree(
    wt_bin: str,
    repo_root: str,
    branch: str,
    dest: str,
    base: str | None,
    timeout_secs: float = SWITCH_TIMEOUT_SECS,
) -> SwitchResult:
    """Create the worktree, or switch to it when the branch already exists."""
    try:
        return switch_worktree(
            wt_bin, repo_root, branch, dest, create=True, base=base, timeout_secs=timeout_secs
        )
    except WorktrunkError as exc:
        if ALREADY_EXISTS_HINT not in str(exc).lower():
            raise
    return switch_worktree(wt_bin, repo_root, branch, dest, create=False, timeout_secs=timeout_secs)
