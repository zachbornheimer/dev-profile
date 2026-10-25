"""worktree-cleanup.py.

Every repo here is a throwaway temp dir, removed by pytest's tmp_path
teardown.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from hook_harness import HOOKS_DIR

PY_HOOK = "worktree-cleanup.py"


def run_cleanup(
    hook: str, worktree_path: str, state_dir: Path
) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "HC_STATE_DIR_OVERRIDE": str(state_dir)}
    return subprocess.run(
        [str(HOOKS_DIR / PY_HOOK)],
        input=f'{{"worktree_path":"{worktree_path}"}}',
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
        check=False,
    )


def build_repo_with_worktree(tmp_path: Path, branch: str) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    subprocess.run(["git", "init", "--quiet", str(repo)], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.email", "test@example.invalid"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.name", "Worktree Cleanup Test"],
        check=True,
    )
    (repo / "seed.txt").write_text("seed\n")
    subprocess.run(["git", "-C", str(repo), "add", "seed.txt"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "--quiet", "-m", "seed"], check=True
    )
    worktree = tmp_path / ".worktrees" / f"repo-{branch.removeprefix('worktree-')}"
    worktree.parent.mkdir(parents=True)
    subprocess.run(
        ["git", "-C", str(repo), "worktree", "add", "-b", branch, str(worktree)],
        check=True,
        capture_output=True,
    )
    return repo, worktree


def test_removes_worktree_and_matching_branch(tmp_path: Path) -> None:
    repo, worktree = build_repo_with_worktree(tmp_path, "worktree-cleanupcase")

    result = run_cleanup(PY_HOOK, str(worktree), tmp_path / "state")

    assert result.returncode == 0, result.stderr
    assert not worktree.exists()
    branches = subprocess.run(
        ["git", "-C", str(repo), "branch", "--list", "worktree-cleanupcase"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout
    assert "worktree-cleanupcase" not in branches


def test_leaves_non_adopted_branch_name_alone(tmp_path: Path) -> None:
    repo, worktree = build_repo_with_worktree(tmp_path, "feature-not-adopted")

    result = run_cleanup(PY_HOOK, str(worktree), tmp_path / "state")

    assert result.returncode == 0, result.stderr
    assert not worktree.exists()
    branches = subprocess.run(
        ["git", "-C", str(repo), "branch", "--list", "feature-not-adopted"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout
    assert "feature-not-adopted" in branches


def test_missing_worktree_path_is_a_silent_no_op(tmp_path: Path) -> None:
    result = run_cleanup(PY_HOOK, str(tmp_path / "does-not-exist"), tmp_path / "state")

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == ""


def test_empty_stdin_is_a_silent_no_op(tmp_path: Path) -> None:
    env = {**os.environ, "HC_STATE_DIR_OVERRIDE": str(tmp_path / "state")}
    result = subprocess.run(
        [str(HOOKS_DIR / PY_HOOK)],
        input="",
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == ""


def test_falls_back_to_rm_rf_when_main_root_is_unresolvable(tmp_path: Path) -> None:
    # A plain directory (not a git worktree at all): git commands against it
    # fail, so the hook must fall back to rm -rf rather than erroring.
    orphan = tmp_path / "orphan-dir"
    orphan.mkdir()
    (orphan / "file.txt").write_text("x\n")

    result = run_cleanup(PY_HOOK, str(orphan), tmp_path / "state")

    assert result.returncode == 0, result.stderr
    assert not orphan.exists()
