#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""PreToolUse (Write|Edit matcher) - keep a worktree-bound session in its worktree.

A child that runs in a git worktree must not write into the repository's main
checkout. A worktree cwd does not stop an absolute path: a work order that
says "copy the files from /path/to/main and write the finished files back"
makes the shared checkout the write target by design (incident: the summarize
focus fix on 2026-10-17, where a delegated child wrote into the parent's
checkout while its order told it to).

The session's cwd decides:

  - cwd inside a linked worktree (its .git is a file whose gitdir is
    <main>/.git/worktrees/<name>): a target under <main> is denied unless it
    is inside the worktree itself.
  - any other cwd (main checkout, non-repo, submodule): silent.

Scratch and home paths outside the main checkout stay allowed; only writes
that land in the shared checkout of the repo this session is isolated from
are refused.

Fails OPEN on any parse error or unexpected input: a false block is far more
costly than a missed check.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))

from hook_common import Decision, HookEvent, run_hook

HOOK_NAME = "worktree-write-guard"
WRITE_TOOLS = frozenset({"Write", "Edit"})
WORKTREES_SEGMENT = "worktrees"
GITDIR_PREFIX = "gitdir:"
REASON = (
    "This write targets '{target}', inside the main checkout of the repo you "
    "were given a worktree for ('{worktree}'). Write inside your worktree; the "
    "main checkout is shared with the parent and other agents. If the file does "
    "not exist in the worktree yet, create it there instead of writing it back "
    "to the shared checkout."
)


def _nearest_repo_marker(start: str) -> Path | None:
    """Walk up from `start` to the nearest directory holding .git."""
    current = Path(os.path.abspath(os.path.expanduser(start)))
    while True:
        marker = current / ".git"
        if marker.is_dir() or marker.is_file():
            return marker
        parent = current.parent
        if parent == current:
            return None
        current = parent


def worktree_roots(cwd: str) -> tuple[Path, Path] | None:
    """(worktree root, main checkout root) when `cwd` is a linked worktree."""
    marker = _nearest_repo_marker(cwd)
    if marker is None or not marker.is_file():
        return None
    try:
        text = marker.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return None
    if not text.startswith(GITDIR_PREFIX):
        return None
    gitdir = Path(text[len(GITDIR_PREFIX):].strip())
    if not gitdir.is_absolute():
        gitdir = (marker.parent / gitdir).resolve()
    parts = gitdir.parts
    if ".git" not in parts:
        return None
    dot_git = parts.index(".git")
    # Submodules point at <super>/.git/modules/<name>; linked worktrees at
    # <main>/.git/worktrees/<name>. Only the latter is isolated from a main
    # checkout this guard should protect.
    if dot_git + 1 >= len(parts) or parts[dot_git + 1] != WORKTREES_SEGMENT:
        return None
    main_root = Path(*parts[:dot_git]) if dot_git else None
    if main_root is None:
        return None
    return marker.parent.resolve(), main_root.resolve()


def _within(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def _resolved_target(target: str, cwd: str) -> Path:
    candidate = Path(os.path.expanduser(target))
    if not candidate.is_absolute():
        candidate = Path(cwd) / candidate
    return candidate.resolve()


def decide(event: HookEvent) -> Decision | None:
    if event.tool_name not in WRITE_TOOLS:
        return None
    target = event.tool_input("file_path")
    cwd = event.field("cwd", "cwd")
    if not target or not cwd:
        return None
    roots = worktree_roots(cwd)
    if roots is None:
        return None
    worktree, main_root = roots
    resolved = _resolved_target(target, cwd)
    if _within(resolved, worktree):
        return None
    if _within(resolved, main_root):
        return Decision.deny(
            REASON.format(target=resolved, worktree=worktree)
        )
    return None


if __name__ == "__main__":
    run_hook(HOOK_NAME, decide)