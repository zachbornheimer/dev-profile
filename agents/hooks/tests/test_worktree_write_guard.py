"""worktree-write-guard.py: a session in a linked worktree must not write into
the repo's main checkout, even via an absolute path."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from hook_harness import HookRunner

PY_HOOK = "worktree-write-guard.py"
DENY = "deny"
SILENT = "none"


def make_repo(root: Path) -> Path:
    root.mkdir(parents=True)
    subprocess.run(["git", "init", "--quiet", str(root)], check=True)
    subprocess.run(
        ["git", "-C", str(root), "config", "user.email", "test@example.invalid"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(root), "config", "user.name", "Worktree Write Guard Test"],
        check=True,
    )
    (root / "seed.txt").write_text("seed\n")
    subprocess.run(["git", "-C", str(root), "add", "seed.txt"], check=True)
    subprocess.run(
        ["git", "-C", str(root), "commit", "--quiet", "-m", "seed"], check=True
    )
    return root


@pytest.fixture
def trees(tmp_path: Path) -> tuple[Path, Path]:
    """(main checkout, linked worktree) with the worktree on its own branch."""
    main = make_repo(tmp_path / "org" / "repo")
    wt = tmp_path / "org" / "repo" / ".worktrees" / "wt1"
    subprocess.run(
        ["git", "-C", str(main), "worktree", "add", "-b", "wt1", str(wt), "HEAD"],
        check=True,
    )
    return main, wt


def run_guard(hooks: HookRunner, cwd: Path, target: str) -> str:
    payload = {
        "tool_name": "write_file",
        "tool_input": {"path": target},
        "cwd": str(cwd),
    }
    run = hooks.run_payload(PY_HOOK, payload)
    assert run.exit_code == 0
    assert run.stderr == ""
    assert not run.failed_open, run.log
    return run.decision


def test_write_into_main_checkout_denied(hooks: HookRunner, trees) -> None:
    main, wt = trees
    target = str(main / "mastra" / "new.ts")
    assert run_guard(hooks, wt, target) == DENY


def test_write_into_worktree_allowed(hooks: HookRunner, trees) -> None:
    _main, wt = trees
    target = str(wt / "new.ts")
    assert run_guard(hooks, wt, target) == SILENT


def test_write_from_main_checkout_silent(hooks: HookRunner, trees) -> None:
    """A session IN the main checkout is not worktree-bound; silent."""
    main, _wt = trees
    target = str(main / "mastra" / "new.ts")
    assert run_guard(hooks, main, target) == SILENT


def test_write_to_scratch_outside_repo_silent(hooks: HookRunner, trees, tmp_path) -> None:
    """Scratch paths outside the main checkout are not the shared tree."""
    _main, wt = trees
    scratch = tmp_path / "scratch" / "note.txt"
    scratch.parent.mkdir()
    assert run_guard(hooks, wt, str(scratch)) == SILENT


def test_write_to_other_repo_silent(hooks: HookRunner, trees, tmp_path) -> None:
    """A target inside a DIFFERENT repo is not this repo's main checkout."""
    _main, wt = trees
    other = make_repo(tmp_path / "other" / "project")
    target = str(other / "file.ts")
    assert run_guard(hooks, wt, target) == SILENT


def test_relative_target_resolves_against_worktree(hooks: HookRunner, trees) -> None:
    """A relative path is resolved against cwd; inside the worktree -> silent."""
    _main, wt = trees
    assert run_guard(hooks, wt, "new.ts") == SILENT


def test_unrelated_tool_silent(hooks: HookRunner, trees) -> None:
    main, wt = trees
    run = hooks.run_payload(
        PY_HOOK,
        {"tool_name": "Read", "tool_input": {"file_path": str(main / "seed.txt")}, "cwd": str(wt)},
    )
    assert run.decision == SILENT


def test_malformed_payload_fails_open(hooks: HookRunner) -> None:
    run = hooks.run_payload(PY_HOOK, "")
    assert run.exit_code == 0
    assert run.decision == SILENT