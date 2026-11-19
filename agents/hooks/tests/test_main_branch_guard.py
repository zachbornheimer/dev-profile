"""Tests for main-branch-guard.py: every managed fork's mirror is read-only."""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

from hook_harness import HOOKS_DIR, HookRunner

HOOK = "main-branch-guard.py"
FORK_CLI = "bun ~/.omp/agent/tools/fork/cli.ts"


def _repo(parent: Path, name: str, branch: str) -> Path:
    repo = parent / name
    repo.mkdir()
    subprocess.run(
        ["git", "-C", str(repo), "init", "-q", "-b", branch],
        check=True,
        capture_output=True,
    )
    return repo


def _commit(repo: Path, message: str) -> str:
    subprocess.run(
        ["git", "-C", str(repo), "commit", "--allow-empty", "-q", "-m", message],
        check=True,
        capture_output=True,
    )
    return subprocess.check_output(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True
    ).strip()


def _managed_fork(
    parent: Path,
    name: str,
    branch: str,
    *,
    origin: str,
    mirror: str = "main",
    upstream: str | None = "sharkdp/hexyl",
    parent_repo: str | None = None,
) -> Path:
    """A checkout shaped like a zachbornheimer fork: origin owner plus a parent."""
    repo = _repo(parent, name, branch)
    mirror_sha = _commit(repo, "upstream mirror")
    subprocess.run(
        ["git", "-C", str(repo), "remote", "add", "origin", origin],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "update-ref",
            f"refs/remotes/origin/{mirror}",
            mirror_sha,
        ],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "config", "fork.mirror", mirror],
        check=True,
        capture_output=True,
    )
    if upstream is not None:
        subprocess.run(
            [
                "git",
                "-C",
                str(repo),
                "remote",
                "add",
                "upstream",
                f"https://github.com/{upstream}.git",
            ],
            check=True,
            capture_output=True,
        )
    if parent_repo is not None:
        (repo / ".git" / "fork-parent").write_text(parent_repo)
    return repo


def _reason(run) -> str:
    return run.output["hookSpecificOutput"]["permissionDecisionReason"]


def _edit(hooks: HookRunner, path: Path, tool: str = "Edit"):
    return hooks.run_payload(
        HOOK,
        {
            "hook_event_name": "PreToolUse",
            "tool_name": tool,
            "tool_input": {
                "file_path": str(path),
                "old_string": "a",
                "new_string": "b",
            },
            "cwd": "/tmp",
        },
    )


def _run_command(hooks: HookRunner, command: str, cwd: str = "/tmp"):
    return hooks.run_payload(
        HOOK,
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "omp_capability_run_command",
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
                "path": "xd://mcp__capability_omp_capability_run_command",
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


def test_denies_push_to_mirror_in_oh_my_pi(hooks: HookRunner, tmp_path: Path) -> None:
    repo = _managed_fork(
        tmp_path,
        "oh-my-pi",
        "feat/x",
        origin="https://github.com/zachbornheimer/oh-my-pi.git",
        upstream="can1357/oh-my-pi",
    )
    run = _run_command(hooks, f"cd {repo} && git push origin main")
    assert run.decision == "deny"
    assert f"{FORK_CLI} land oh-my-pi" in _reason(run)


def test_denies_direct_commit_and_cherry_pick_on_integration_branch_in_any_fork(
    hooks: HookRunner, tmp_path: Path
) -> None:
    repo = _repo(tmp_path, "any-fork", "assembled")
    for command in (
        f"cd {repo} && git commit -m 'direct feature on assembled'",
        f"cd {repo} && git cherry-pick abc1234",
        f"cd {repo} && git rebase origin/main",
        f"cd {repo} && wt step commit",
    ):
        run = _run_command(hooks, command)
        assert run.decision == "deny", command
        assert (
            "Integration branches (`assembled`, `next`, `seen`)"
            in run.output["hookSpecificOutput"]["permissionDecisionReason"]
        )


def test_allows_merge_and_merge_commit_completion_on_integration_branch(
    hooks: HookRunner, tmp_path: Path
) -> None:
    repo = _repo(tmp_path, "any-fork", "assembled")
    run = _run_command(hooks, f"cd {repo} && git merge origin/main")
    assert run.decision == "none"

    # Simulate an in-progress merge (MERGE_HEAD present): completing the merge commit is allowed.
    (repo / ".git" / "MERGE_HEAD").write_text("0" * 40 + "\n")
    run_commit = _run_command(hooks, f"cd {repo} && git commit --no-edit")
    assert run_commit.decision == "none"


def test_denies_non_merge_push_to_assembled_and_allows_merge_push(
    hooks: HookRunner, tmp_path: Path
) -> None:
    repo = _repo(tmp_path, "any-fork", "assembled")
    empty_tree = subprocess.check_output(
        ["git", "-C", str(repo), "hash-object", "-t", "tree", "/dev/null"],
        text=True,
    ).strip()
    single_sha = subprocess.check_output(
        ["git", "-C", str(repo), "commit-tree", empty_tree, "-m", "initial"],
        text=True,
    ).strip()
    subprocess.run(
        ["git", "-C", str(repo), "update-ref", "refs/heads/assembled", single_sha],
        check=True,
    )
    # Single-parent commit on assembled cannot be pushed to assembled.
    run_single = _run_command(hooks, f"cd {repo} && git push origin HEAD:assembled")
    assert run_single.decision == "deny"

    # Create a two-parent merge commit and verify pushing it to assembled is allowed.
    second_sha = subprocess.check_output(
        ["git", "-C", str(repo), "commit-tree", empty_tree, "-m", "second"],
        text=True,
    ).strip()
    merge_sha = subprocess.check_output(
        [
            "git",
            "-C",
            str(repo),
            "commit-tree",
            empty_tree,
            "-p",
            single_sha,
            "-p",
            second_sha,
            "-m",
            "Merge origin/main into assembled",
        ],
        text=True,
    ).strip()
    run_merge = _run_command(
        hooks, f"cd {repo} && git push origin {merge_sha}:assembled"
    )
    assert run_merge.decision == "none"


def test_denies_wt_merge_and_wt_land_on_a_fork_mirror(
    hooks: HookRunner, tmp_path: Path
) -> None:
    repo = _managed_fork(
        tmp_path,
        "oh-my-pi",
        "main",
        origin="https://github.com/zachbornheimer/oh-my-pi.git",
        upstream="can1357/oh-my-pi",
    )
    for command in (
        f"cd {repo} && wt merge",
        f"wt -C {repo} merge",
        f"cd {repo} && wt land",
    ):
        run = _run_command(hooks, command)
        assert run.decision == "deny", command
        assert f"{FORK_CLI} change oh-my-pi" in _reason(run)


def test_allows_topic_push_in_oh_my_pi(hooks: HookRunner, tmp_path: Path) -> None:
    repo = _repo(tmp_path, "oh-my-pi", "feat/x")
    run = _run_command(hooks, f"cd {repo} && git push fork feat/my-topic")
    assert run.decision == "none"


def test_topic_branch_commit_in_oh_my_pi_is_allowed(
    hooks: HookRunner, tmp_path: Path
) -> None:
    repo = _repo(tmp_path, "oh-my-pi", "feat/x")
    run = _run_command(hooks, f"cd {repo} && git commit -m 'topic work'")
    assert run.decision == "none"


def test_denies_commit_on_mirror_of_a_non_omp_fork(
    hooks: HookRunner, tmp_path: Path
) -> None:
    repo = _managed_fork(
        tmp_path,
        "hexyl",
        "main",
        origin="https://github.com/zachbornheimer/hexyl.git",
    )
    run = _run_command(hooks, f"cd {repo} && git commit -m 'direct commit on mirror'")
    assert run.decision == "deny"
    reason = _reason(run)
    assert f"{FORK_CLI} change hexyl" in reason, (reason, run.log, run.stderr)
    assert f"{FORK_CLI} land hexyl" in reason
    assert f"{FORK_CLI} sync hexyl" in reason
    assert "never use branch protection" in reason


def test_allows_commit_on_topic_branch_of_a_non_omp_fork(
    hooks: HookRunner, tmp_path: Path
) -> None:
    repo = _managed_fork(
        tmp_path,
        "hexyl",
        "feat/color",
        origin="git@github.com:zachbornheimer/hexyl.git",
    )
    run = _run_command(hooks, f"cd {repo} && git commit -m 'topic work'")
    assert run.decision == "none"


def test_allows_ff_only_pull_on_a_fork_mirror(
    hooks: HookRunner, tmp_path: Path, monkeypatch
) -> None:
    repo = _managed_fork(
        tmp_path,
        "hexyl",
        "main",
        origin="https://github.com/zachbornheimer/hexyl.git",
    )
    monkeypatch.setenv("DEV_PROFILE_ALLOW_DEFAULT_BRANCH_COMMIT", "1")
    for command in (
        f"cd {repo} && git merge --ff-only origin/main",
        f"git -C {repo} pull --ff-only",
        f"cd {repo} && gh repo sync",
    ):
        run = _run_command(hooks, command)
        assert run.decision == "none", command


def test_denies_edit_inside_a_fork_mirror_checkout(
    hooks: HookRunner, tmp_path: Path
) -> None:
    repo = _managed_fork(
        tmp_path,
        "hexyl",
        "main",
        origin="https://github.com/zachbornheimer/hexyl.git",
        parent_repo="sharkdp/hexyl",
        upstream=None,
    )
    target = repo / "src" / "main.rs"
    target.parent.mkdir()
    target.write_text("fn main() {}\n")
    run = _edit(hooks, target)
    assert run.decision == "deny"
    assert f"{FORK_CLI} change hexyl" in _reason(run)


def test_allows_edit_on_a_fork_topic_branch(hooks: HookRunner, tmp_path: Path) -> None:
    repo = _managed_fork(
        tmp_path,
        "hexyl",
        "feat/color",
        origin="https://github.com/zachbornheimer/hexyl.git",
    )
    target = repo / "src" / "main.rs"
    target.parent.mkdir()
    target.write_text("fn main() {}\n")
    assert _edit(hooks, target, "Write").decision == "none"


def test_fork_detection_is_cached(tmp_path: Path) -> None:
    import sys

    repo = _managed_fork(
        tmp_path,
        "hexyl",
        "main",
        origin="https://github.com/zachbornheimer/hexyl.git",
    )
    sys.path.insert(0, str(HOOKS_DIR / "lib"))
    import managed_fork as module

    assert module.managed_fork(str(repo)) == {"name": "hexyl", "mirror": "main"}
    started = time.perf_counter()
    for _ in range(20):
        assert module.managed_fork(str(repo))["mirror"] == "main"
    elapsed_ms = (time.perf_counter() - started) * 1000 / 20
    assert elapsed_ms < 5, elapsed_ms


def test_machine_setup_does_not_install_a_clone_hook() -> None:
    script = (
        Path(__file__).resolve().parents[3] / "bin" / "dev-profile-omp-machine-setup"
    )
    text = script.read_text()
    assert "cat >" not in text
    assert "install_fork_reference_transaction_hook" not in text
    assert "chmod +x" not in text
