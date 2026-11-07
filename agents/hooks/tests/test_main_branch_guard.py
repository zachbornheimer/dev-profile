"""Tests for main-branch-guard.py and the reference-transaction hook that
keeps oh-my-pi's `main` a read-only mirror."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from hook_harness import HookRunner

HOOK = "main-branch-guard.py"


def _repo(parent: Path, name: str, branch: str) -> Path:
    repo = parent / name
    repo.mkdir()
    subprocess.run(
        ["git", "-C", str(repo), "init", "-q", "-b", branch],
        check=True,
        capture_output=True,
    )
    return repo


def _run_command(hooks: HookRunner, command: str, cwd: str = "/tmp"):
    return hooks.run_payload(
        HOOK,
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "agentmux_capability_run_command",
            "tool_input": {"command": command},
            "cwd": cwd,
        },
    )


def test_denies_commit_on_main_in_any_repository(
    hooks: HookRunner, tmp_path: Path
) -> None:
    repo = _repo(tmp_path, "some-repo", "main")
    run = _run_command(hooks, f"cd {repo} && git commit -m 'direct commit on main'")
    assert run.decision == "deny"
    assert (
        "wt switch --create"
        in run.output["hookSpecificOutput"]["permissionDecisionReason"]
    )


def test_denies_push_to_main_in_any_repository(
    hooks: HookRunner, tmp_path: Path
) -> None:
    repo = _repo(tmp_path, "some-repo", "feat/x")
    for command in (
        f"git -C {repo} push origin main",
        f"git -C {repo} push origin HEAD:main",
        f"git -C {repo} push origin HEAD:refs/heads/master",
    ):
        run = _run_command(hooks, command)
        assert run.decision == "deny", command


def test_denies_push_to_main_through_the_write_bridge(
    hooks: HookRunner, tmp_path: Path
) -> None:
    repo = _repo(tmp_path, "some-repo", "feat/x")
    run = hooks.run_payload(
        HOOK,
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "write",
            "tool_input": {
                "path": "xd://mcp__capability_agentmux_capability_run_command",
                "content": json.dumps({"command": f"git -C {repo} push origin main"}),
            },
        },
    )
    assert run.decision == "deny"


def test_allows_topic_branch_commit_and_push(hooks: HookRunner, tmp_path: Path) -> None:
    repo = _repo(tmp_path, "some-repo", "feat/x")
    for command in (
        f"git -C {repo} commit -m 'topic work'",
        f"git -C {repo} push -u origin feat/x",
        f"git -C {repo} merge origin/main",
    ):
        run = _run_command(hooks, command)
        assert run.decision == "none", command


def test_allows_read_only_merge_plumbing_and_recovery(
    hooks: HookRunner, tmp_path: Path
) -> None:
    repo = _repo(tmp_path, "some-repo", "main")
    for command in (
        f"cd {repo} && git merge-base --is-ancestor feat/x origin/main",
        f"git -C {repo} merge-tree --write-tree origin/main feat/x",
        f"git -C {repo} merge --abort",
        f"git -C {repo} reset --soft HEAD~1",
    ):
        run = _run_command(hooks, command)
        assert run.decision == "none", command


def test_allows_wt_land_outside_oh_my_pi(hooks: HookRunner, tmp_path: Path) -> None:
    repo = _repo(tmp_path, "some-repo", "feat/x")
    run = _run_command(hooks, f"wt -C {repo} land")
    assert run.decision == "none"


def test_denies_push_to_fork_main_in_oh_my_pi(
    hooks: HookRunner, tmp_path: Path
) -> None:
    repo = _repo(tmp_path, "oh-my-pi", "feat/x")
    run = _run_command(hooks, f"cd {repo} && git push fork main")
    assert run.decision == "deny"
    assert (
        "omp-rebuild.toml"
        in run.output["hookSpecificOutput"]["permissionDecisionReason"]
    )


def test_denies_wt_merge_and_wt_land_in_oh_my_pi(
    hooks: HookRunner, tmp_path: Path
) -> None:
    repo = _repo(tmp_path, "oh-my-pi", "feat/x")
    for command in (
        f"cd {repo} && wt merge",
        f"wt -C {repo} merge",
        f"cd {repo} && wt land",
    ):
        run = _run_command(hooks, command)
        assert run.decision == "deny", command


def test_allows_topic_push_and_omp_build_in_oh_my_pi(
    hooks: HookRunner, tmp_path: Path
) -> None:
    repo = _repo(tmp_path, "oh-my-pi", "omp-build")
    run = _run_command(hooks, f"cd {repo} && git push fork feat/my-topic omp-build")
    assert run.decision == "none"


def test_topic_branch_commit_in_oh_my_pi_is_allowed(
    hooks: HookRunner, tmp_path: Path
) -> None:
    repo = _repo(tmp_path, "oh-my-pi", "feat/x")
    run = _run_command(hooks, f"cd {repo} && git commit -m 'topic work'")
    assert run.decision == "none"


def test_git_reference_transaction_hook_blocks_non_upstream_main_mutation() -> None:
    omp_repo = Path.home() / "Developer" / "Personal" / "oh-my-pi"
    hook_file = omp_repo / ".git" / "hooks" / "reference-transaction"
    assert hook_file.is_file()
    proc = subprocess.run(
        ["git", "-C", str(omp_repo), "update-ref", "refs/heads/main", "omp-build"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert proc.returncode != 0
    assert "refs/heads/main is read-only and must match origin/main" in proc.stderr
