#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""WorktreeRemove — cleanup counterpart to worktree-provision.py.

Once ANY WorktreeCreate hook is registered, Claude Code stops doing its own
`git worktree remove` even though these are still ordinary git worktrees —
this hook does that removal, plus the matching `worktree-<name>` branch
worktree-provision.py created.

No decision control (per code.claude.com/docs/en/hooks.md's WorktreeRemove
section): output is discarded, and the input schema only guarantees
`worktree_path`. Every step here is best-effort; this always exits 0.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))

from hook_common import (
    Clock,
    HookEvent,
    HookLog,
    HookSettings,
    read_stdin,
    run_fail_open,
)
from worktree_cleanup_git import CleanupGitFacade
from worktree_cleanup_worktrunk import remove_worktree as wt_remove_worktree

HOOK_NAME = "worktree-cleanup"
ADOPTED_BRANCH_PREFIX = "worktree-"


def main_root_of(common_dir: str) -> str:
    return str(Path(common_dir).parent) if common_dir.endswith("/.git") else common_dir


def main() -> None:
    settings = HookSettings.from_env()
    log = HookLog(HOOK_NAME, settings, Clock.from_env())
    git = CleanupGitFacade()

    raw = read_stdin(settings.stdin_timeout_secs)
    if not raw:
        return
    event = HookEvent.parse(raw)
    if event is None:
        return

    worktree_path = event.field("worktree_path", "worktreePath")
    if not worktree_path or not Path(worktree_path).is_dir():
        return

    branch = git.current_branch(worktree_path)
    common_dir = git.common_dir(worktree_path)
    main_root = main_root_of(common_dir) if common_dir else ""

    delete_branch = branch.startswith(ADOPTED_BRANCH_PREFIX)
    if wt_remove_worktree(worktree_path, delete_branch=delete_branch):
        log.record("remove", f"{worktree_path} via wt remove delete_branch={delete_branch}")
        return

    if main_root and git.remove_worktree(main_root, worktree_path):
        log.record("remove", f"{worktree_path} via git worktree remove")
    else:
        git.remove_directory(worktree_path)
        log.record("remove-fallback", f"{worktree_path} via rm -rf (main_root={main_root})")

    if delete_branch and main_root:
        if git.delete_branch(main_root, branch):
            log.record("branch-delete", branch)
        else:
            log.record("branch-delete-warn", branch)


if __name__ == "__main__":
    run_fail_open(HOOK_NAME, main)
