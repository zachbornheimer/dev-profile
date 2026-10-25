#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""SessionStart — give every git repo a local, never-committed beads workspace.

If the session's cwd is in a non-bare git repo and ``bd where`` finds no
workspace, start ``bd init --stealth ...`` detached at the repo's main
checkout so session start never waits on it. Skips $HOME itself, tmp and
Library paths, and Gas City worktrees (gc manages those). Never prints,
never blocks; fails open on any error (via run_hook).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))

from beads_workspace import BeadsWorkspace
from hook_common import GIT, Clock, Decision, HookEvent, HookLog, HookSettings, run_hook

HOOK_NAME = "ensure-beads"
EXCLUDED_ROOTS_ENV = "ENSURE_BEADS_EXCLUDED_ROOTS"
DEFAULT_EXCLUDED_ROOTS = (
    Path.home() / "Library",
    Path("/private/tmp"),
    Path("/private/var/tmp"),
    Path("/tmp"),
)
GC_WORKTREES_MARKER = "/.gc/worktrees/"


def _excluded_roots() -> tuple[Path, ...]:
    override = os.environ.get(EXCLUDED_ROOTS_ENV)
    if override is None:
        return DEFAULT_EXCLUDED_ROOTS
    return tuple(Path(part) for part in override.split(os.pathsep) if part)


def _is_excluded(directory: Path) -> bool:
    if directory == Path.home().resolve():
        return True
    if GC_WORKTREES_MARKER in f"{directory}/":
        return True
    return any(directory.is_relative_to(root.resolve()) for root in _excluded_roots())


def _main_checkout(directory: Path) -> tuple[Path, Path] | None:
    """(main checkout root, git common dir) for a non-bare repo containing ``directory``."""
    if GIT.run(str(directory), "rev-parse", "--is-bare-repository").text != "false":
        return None
    common = GIT.run(
        str(directory), "rev-parse", "--path-format=absolute", "--git-common-dir"
    ).text
    if not common:
        return None
    return Path(common).parent, Path(common)


def decide(event: HookEvent) -> Decision | None:
    cwd = event.field("cwd", "cwd")
    if not cwd or not Path(cwd).is_dir():
        return None
    directory = Path(cwd).resolve()
    if _is_excluded(directory):
        return None
    located = _main_checkout(directory)
    if located is None:
        return None
    repo_root, git_dir = located
    if _is_excluded(repo_root.resolve()):
        return None

    workspace = BeadsWorkspace(repo_root=repo_root, lock_dir=git_dir)
    if workspace.exists_for(directory):
        return None
    started = workspace.start_init_in_background()
    HookLog(HOOK_NAME, HookSettings.from_env(), Clock.from_env()).record(
        "init-started" if started else "init-locked", str(repo_root)
    )
    return None


if __name__ == "__main__":
    run_hook(HOOK_NAME, decide)
