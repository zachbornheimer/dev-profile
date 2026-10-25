"""worktree-provision.py: cases ported from the former tests/worktree-provision-adopt.sh
and tests/worktree-provision-nonrepo.sh.

Asserts stdout (the last non-empty line, the load-bearing WorktreeCreate
contract) and worktree end-state. Every repo here is a throwaway temp dir.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from hook_harness import HOOKS_DIR

sys.path.insert(0, str(HOOKS_DIR / "lib"))

from worktree_provision_worktrunk import parse_switch_json

PY_HOOK = "worktree-provision.py"


def last_nonempty_line(text: str) -> str:
    lines = [line for line in text.splitlines() if line.strip()]
    return lines[-1] if lines else ""


def run_provision(
    hook: str,
    cwd: str,
    name: str,
    state_dir: Path,
    env_overrides: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    state_dir.mkdir(parents=True, exist_ok=True)
    env = {
        "HOME": os.environ["HOME"],
        "PATH": os.environ["PATH"],
        "TMPDIR": os.environ.get("TMPDIR", "/tmp"),
        "HC_STATE_DIR_OVERRIDE": str(state_dir),
        **(env_overrides or {}),
    }
    return subprocess.run(
        [str(HOOKS_DIR / hook)],
        input=f'{{"name":"{name}","cwd":"{cwd}"}}',
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
        check=False,
    )


def worktree_exists_on_branch(repo: Path, path: str, branch: str) -> bool:
    result = subprocess.run(
        ["git", "-C", str(repo), "worktree", "list", "--porcelain"],
        capture_output=True,
        text=True,
        check=False,
    )
    at_path = False
    for line in result.stdout.splitlines():
        if line.startswith("worktree "):
            at_path = line[len("worktree ") :] == path
        elif at_path and line == f"branch refs/heads/{branch}":
            return True
    return False


def build_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    subprocess.run(["git", "init", "--quiet", str(repo)], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.email", "test@example.invalid"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.name", "Worktree Provision Test"],
        check=True,
    )
    (repo / "seed.txt").write_text("seed\n")
    subprocess.run(["git", "-C", str(repo), "add", "seed.txt"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "--quiet", "-m", "seed"], check=True
    )
    return repo


def test_adopts_precreated_branch(tmp_path: Path) -> None:
    repo = build_repo(tmp_path)
    branch = "worktree-adoptcase"
    precreated = repo / ".claude" / "worktrees" / "agent-adoptcase"
    precreated.parent.mkdir(parents=True)
    subprocess.run(
        ["git", "-C", str(repo), "worktree", "add", "-b", branch, str(precreated)],
        check=True,
        capture_output=True,
    )

    expected_dest = str(tmp_path / ".worktrees" / "repo-adoptcase")
    result = run_provision(PY_HOOK, str(repo), "adoptcase", tmp_path / "state")

    assert result.returncode == 0, result.stderr
    assert last_nonempty_line(result.stdout) == expected_dest
    assert worktree_exists_on_branch(repo, expected_dest, branch)


def test_happy_path_no_preexisting_branch(tmp_path: Path) -> None:
    repo = build_repo(tmp_path)
    expected_dest = str(tmp_path / ".worktrees" / "repo-freshcase")

    result = run_provision(PY_HOOK, str(repo), "freshcase", tmp_path / "state")

    assert result.returncode == 0, result.stderr
    assert last_nonempty_line(result.stdout) == expected_dest
    assert worktree_exists_on_branch(repo, expected_dest, "worktree-freshcase")


def test_reuses_existing_canonical_worktree(tmp_path: Path) -> None:
    repo = build_repo(tmp_path)
    expected_dest = str(tmp_path / ".worktrees" / "repo-reuse")
    first = run_provision(PY_HOOK, str(repo), "reuse", tmp_path / "state")
    assert first.returncode == 0, first.stderr
    second = run_provision(PY_HOOK, str(repo), "reuse", tmp_path / "state-2")
    assert second.returncode == 0, second.stderr
    assert last_nonempty_line(second.stdout) == expected_dest
    assert worktree_exists_on_branch(repo, expected_dest, "worktree-reuse")


def test_missing_wt_fails_closed(tmp_path: Path) -> None:
    repo = build_repo(tmp_path)
    result = run_provision(
        PY_HOOK,
        str(repo),
        "nowt",
        tmp_path / "state",
        {"WORKTREE_PROVISION_WT": ""},
    )
    assert result.returncode != 0
    assert "wt (worktrunk) is not on PATH" in result.stderr


def test_chezmoi_live_cwd_provisions_backing_repo(tmp_path: Path) -> None:
    source_repo = tmp_path / "dotfiles"
    subprocess.run(["git", "init", "--quiet", str(source_repo)], check=True)
    subprocess.run(
        ["git", "-C", str(source_repo), "config", "user.email", "test@example.invalid"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(source_repo), "config", "user.name", "Nonrepo Test"],
        check=True,
    )
    tracked = source_repo / "home" / "dot_agents" / "hooks" / "completion-gate.py"
    tracked.parent.mkdir(parents=True)
    tracked.write_text("live-content\n")
    subprocess.run(
        [
            "git",
            "-C",
            str(source_repo),
            "add",
            "home/dot_agents/hooks/completion-gate.py",
        ],
        check=True,
    )
    subprocess.run(
        [
            "git",
            "-C",
            str(source_repo),
            "commit",
            "--quiet",
            "-m",
            "seed chezmoi source",
        ],
        check=True,
    )

    live_tree = tmp_path / "agents-live"
    live_tree.mkdir()
    state_dir = tmp_path / "state"

    expected_dest = str(tmp_path / ".worktrees" / "dotfiles-chezmoicase")
    scratch_would_be = state_dir / "bridge-worktrees" / "chezmoicase"

    result = run_provision(
        PY_HOOK,
        str(live_tree),
        "chezmoicase",
        state_dir,
        {
            "WORKTREE_CHEZMOI_LIVE_ROOTS": str(live_tree),
            "CHEZMOI_SOURCE_REPO": str(source_repo),
        },
    )

    assert result.returncode == 0, result.stderr
    assert last_nonempty_line(result.stdout) == expected_dest
    assert not scratch_would_be.is_dir()
    assert (
        Path(expected_dest) / "home" / "dot_agents" / "hooks" / "completion-gate.py"
    ).is_file()


def test_chezmoi_target_without_backing_repo_fails_closed(tmp_path: Path) -> None:
    live_tree = tmp_path / "claude-live"
    live_tree.mkdir()
    state_dir = tmp_path / "state"
    scratch_would_be = state_dir / "bridge-worktrees" / "missingbacking"

    result = run_provision(
        PY_HOOK,
        str(live_tree),
        "missingbacking",
        state_dir,
        {
            "WORKTREE_CHEZMOI_LIVE_ROOTS": str(live_tree),
            "CHEZMOI_SOURCE_REPO": str(tmp_path / "does-not-exist"),
        },
    )

    assert result.returncode != 0
    assert not scratch_would_be.is_dir()
    assert "isolation none" in result.stderr


def test_genuine_bridge_cwd_gets_disposable_scratch(tmp_path: Path) -> None:
    bridge_cwd = tmp_path / "not-a-repo"
    bridge_cwd.mkdir()
    state_dir = tmp_path / "state"
    expected = str(state_dir / "bridge-worktrees" / "bridgecase")

    result = run_provision(PY_HOOK, str(bridge_cwd), "bridgecase", state_dir)

    assert result.returncode == 0, result.stderr
    assert last_nonempty_line(result.stdout) == expected


def test_parse_switch_json_takes_first_object_before_human_line() -> None:
    stdout = (
        '{"action":"created","branch":"freshcase","path":"/tmp/wt"}\n'
        "✓ Created branch freshcase from main and worktree @ /tmp/wt\n"
    )
    assert parse_switch_json(stdout)["path"] == "/tmp/wt"
