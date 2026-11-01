"""Tests for omp-main-branch-guard.py enforcing zero custom commits or pushes on oh-my-pi main."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from hook_harness import HookRunner

HOOK = "omp-main-branch-guard.py"


def test_denies_push_to_fork_main_in_oh_my_pi(hooks: HookRunner) -> None:
    run = hooks.run_payload(
        HOOK,
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "agentmux_capability_run_command",
            "tool_input": {"command": "cd ~/Developer/Personal/oh-my-pi && git push fork main"},
        },
    )
    assert run.decision == "deny"
    assert "omp-rebuild.toml" in (run.output or {})["hookSpecificOutput"]["permissionDecisionReason"]


def test_denies_xd_write_push_to_main_in_oh_my_pi(hooks: HookRunner) -> None:
    run = hooks.run_payload(
        HOOK,
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "write",
            "tool_input": {
                "path": "xd://mcp__capability_agentmux_capability_run_command",
                "content": json.dumps({"command": "git -C ~/Developer/Personal/oh-my-pi push fork HEAD:main"}),
            },
        },
    )
    assert run.decision == "deny"


def test_denies_commit_when_oh_my_pi_checkout_is_on_main(hooks: HookRunner, tmp_path: Path) -> None:
    repo = tmp_path / "oh-my-pi"
    repo.mkdir()
    subprocess.run(["git", "-C", str(repo), "init", "-b", "main"], check=True, capture_output=True)
    run = hooks.run_payload(
        HOOK,
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "agentmux_capability_run_command",
            "tool_input": {"command": f"cd {repo} && git commit -m 'bad commit on main'"},
        },
    )
    assert run.decision == "deny"


def test_allows_push_of_topic_branch_and_omp_build(hooks: HookRunner, tmp_path: Path) -> None:
    repo = tmp_path / "oh-my-pi"
    repo.mkdir()
    subprocess.run(["git", "-C", str(repo), "init", "-b", "omp-build"], check=True, capture_output=True)
    run = hooks.run_payload(
        HOOK,
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "agentmux_capability_run_command",
            "tool_input": {"command": f"cd {repo} && git push fork feat/my-topic omp-build"},
        },
    )
    assert run.decision == "none"
