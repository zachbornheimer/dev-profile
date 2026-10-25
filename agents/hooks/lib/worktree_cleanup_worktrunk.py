"""wt remove adapter for WorktreeRemove. Best-effort: caller falls back to git."""

from __future__ import annotations

import shutil
import subprocess

REMOVE_TIMEOUT_SECS = 60.0


def remove_worktree(
    worktree_path: str, *, delete_branch: bool, timeout_secs: float = REMOVE_TIMEOUT_SECS
) -> bool:
    """True when wt removed the worktree. False when wt is missing or refused."""
    wt_bin = shutil.which("wt")
    if wt_bin is None:
        return False
    argv = [
        wt_bin,
        "-C",
        worktree_path,
        "remove",
        "--foreground",
        "-y",
        "--no-hooks",
        "--force",
        "--format=json",
    ]
    if delete_branch:
        argv.append("-D")
    else:
        argv.append("--no-delete-branch")
    argv.append(worktree_path)
    try:
        done = subprocess.run(
            argv, capture_output=True, text=True, timeout=timeout_secs, check=False
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return done.returncode == 0
