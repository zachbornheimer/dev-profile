"""worktree-lifecycle-guard.py: raw git branch/worktree lifecycle goes through `wt`."""

from __future__ import annotations

import pytest
from hook_harness import HookRun, HookRunner

PY_HOOK = "worktree-lifecycle-guard.py"
DENY = "deny"
SILENT = "none"

# command -> the `wt` replacement the deny reason must name.
DENIED: dict[str, str] = {
    "git worktree add ../.worktrees/repo-x -b x": "wt switch --create",
    "git worktree remove ../.worktrees/repo-x": "wt remove",
    "git worktree prune": "wt step prune",
    "git worktree move a b": "wt step relocate",
    "git checkout -b feature": "wt switch --create",
    "git checkout -B feature origin/main": "wt switch --create",
    "git checkout --orphan gh-pages": "wt switch --create",
    "git checkout main": "wt switch",
    "git checkout -": "wt switch",
    "git switch main": "wt switch",
    "git switch -c feature": "wt switch --create",
    "git branch feature": "wt switch --create",
    "git branch feature origin/main": "wt switch --create",
    "git branch -c old new": "wt switch --create",
    "git branch -d feature": "wt remove",
    "git branch -D feature": "wt remove",
    "git branch --delete feature": "wt remove",
    "git merge feature": "wt merge",
    "git merge --squash feature": "wt merge",
    "git rebase main": "wt step rebase",
    "git rebase -i HEAD~3": "wt step rebase",
    "git rebase --onto main old feature": "wt sync",
    "gh pr checkout 123": "wt switch pr:",
    "git add -A": "wt step commit",
    "git add src/app.py": "wt step commit",
    "git stage .": "wt step commit",
    "git commit -m 'feat: add x'": "wt step commit",
    "git commit -am 'feat: add x'": "wt step commit --stage tracked",
    "git commit -a -m x": "wt step commit --stage tracked",
    "git push": "wt sync --push-only",
    "git push origin feature": "wt sync --push-only",
    "git -C repo push --force-with-lease": "wt sync --push-only",
    "git add -A && git commit -m x": "wt step commit",
    "git -C ~/Developer/Personal/zq commit -S -m x": "wt step commit",
    "HUSKY=0 git commit -m x": "wt step commit",
    "bash -c 'git add . && git commit -m x'": "wt step commit",
    "(cd repo && git commit -m x)": "wt step commit",
    # Invocation shapes the guard must see through.
    "git -C ~/Developer/Personal/zq checkout -b x": "wt switch --create",
    "git -c core.editor=true rebase main": "wt step rebase",
    "/usr/bin/git switch main": "wt switch",
    "cd repo && git checkout -b x": "wt switch --create",
    "cd repo&&git checkout -b x": "wt switch --create",
    "git status; git switch main": "wt switch",
    "git fetch\ngit merge origin/main": "wt merge",
    "GIT_TRACE=1 git switch main": "wt switch",
    "env GIT_TRACE=1 git switch main": "wt switch",
    "command git switch main": "wt switch",
    "(cd repo && git branch -D x)": "wt remove",
    "echo $(git checkout -b x)": "wt switch --create",
    "bash -c 'git checkout -b x'": "wt switch --create",
    'zsh -lc "cd r && git worktree add ../.worktrees/r-x"': "wt switch --create",
}

ALLOWED = (
    "git status",
    "git log --oneline -5",
    "git diff main...HEAD",
    "git commit --amend --no-edit",
    "git add --dry-run .",
    "git commit --help",
    "git push -u origin feature",
    "git push --set-upstream origin feature",
    "git push --dry-run",
    "git push origin --delete old",
    "git fetch origin",
    "git pull --ff-only",
    "git stash push -u",
    "git worktree list",
    "git worktree lock ../.worktrees/r-x",
    "git checkout -- src/app.py",
    "git checkout main -- src/app.py",
    "git checkout HEAD~1 src/app.py README.md",
    "git checkout -p src/app.py",
    "git checkout --ours src/app.py",
    "git restore src/app.py",
    "git branch",
    "git branch -a",
    "git branch -vv",
    "git branch --show-current",
    "git branch --list 'feat/*'",
    "git branch --merged main",
    "git branch --contains abc123",
    "git branch --format='%(refname:short)'",
    "git branch -m old new",
    "git branch -u origin/main",
    "git branch --set-upstream-to=origin/main",
    "git merge --abort",
    "git merge --continue",
    "git merge-base main HEAD",
    "git rebase --continue",
    "git rebase --abort",
    "git rebase --skip",
    "git switch --help",
    "gh pr view 123",
    "gh pr checks 123",
    "wt switch --create feature",
    "wt merge",
    "wt step for-each -- git status",
    "wt sync --fetch",
    "workz start feature",
    "echo 'git checkout -b x'",
    "git log --grep='run git switch main next'",
    "echo 'git commit -m x'",
    "wt step commit",
    "wt step commit --stage tracked",
    "rg 'git checkout -b' docs/",
    "cat <<'EOF' > notes.md\ngit checkout -b x\ngit branch -D y\nEOF",
)


def _bash(command: str) -> dict:
    return {"tool_name": "Bash", "tool_input": {"command": command}}


def _reason(run: HookRun) -> str:
    specific = (run.output or {}).get("hookSpecificOutput", {})
    return specific.get("permissionDecisionReason", "")


def assert_clean_run(run: HookRun) -> None:
    assert run.exit_code == 0
    assert run.stderr == ""
    assert not run.failed_open, run.log


@pytest.mark.parametrize(("command", "replacement"), DENIED.items(), ids=list(DENIED))
def test_denies_raw_lifecycle_git_and_names_wt_replacement(
    hooks: HookRunner, command: str, replacement: str
) -> None:
    run = hooks.run_payload(PY_HOOK, _bash(command))

    assert_clean_run(run)
    assert run.decision == DENY, run.stdout
    assert replacement in _reason(run)


@pytest.mark.parametrize("command", ALLOWED)
def test_allows_git_that_worktrunk_does_not_replace(
    hooks: HookRunner, command: str
) -> None:
    run = hooks.run_payload(PY_HOOK, _bash(command))

    assert_clean_run(run)
    assert run.decision == SILENT, run.stdout


@pytest.mark.parametrize(
    "payload",
    [
        {
            "toolName": "run_terminal_command",
            "toolInput": {"command": "git switch main"},
        },
        {
            "tool_name": "Bash",
            "tool_input": {"command": "git switch main"},
            "cwd": "/tmp",
        },
    ],
    ids=["grok-camelcase", "codex-snake"],
)
def test_denies_across_harness_payload_shapes(hooks: HookRunner, payload: dict) -> None:
    run = hooks.run_payload(PY_HOOK, payload)

    assert_clean_run(run)
    assert run.decision == DENY, run.stdout


@pytest.mark.parametrize(
    "payload",
    ["", {"tool_name": "Read", "tool_input": {"file_path": "/x"}}, _bash("")],
    ids=["empty-stdin", "unrelated-tool", "empty-command"],
)
def test_stays_silent_on_non_bash_input(hooks: HookRunner, payload: object) -> None:
    run = hooks.run_payload(PY_HOOK, payload)

    assert_clean_run(run)
    assert run.decision == SILENT, run.stdout


def test_deny_reason_does_not_advertise_a_bypass(hooks: HookRunner) -> None:
    run = hooks.run_payload(PY_HOOK, _bash("git checkout -b x"))

    assert "ALLOW" not in _reason(run)
    assert "=1" not in _reason(run)


def test_denies_command_sent_as_argv_array(hooks: HookRunner) -> None:
    payload = {
        "tool_name": "Bash",
        "tool_input": {"command": ["/bin/zsh", "-lc", "git switch main"]},
    }

    run = hooks.run_payload(PY_HOOK, payload)

    assert_clean_run(run)
    assert run.decision == DENY, run.stdout


# --- staging is plain git while an operation is mid-flight (conflict resolution) ---

IN_PROGRESS_MARKERS = (
    ("rebase-merge", True),
    ("rebase-apply", True),
    ("MERGE_HEAD", False),
    ("CHERRY_PICK_HEAD", False),
)


def _repo(tmp_path, marker: str | None = None, is_dir: bool = False):
    import subprocess

    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    if marker:
        target = repo / ".git" / marker
        target.mkdir() if is_dir else target.write_text("x\n")
    return repo


def _bash_in(command: str, cwd) -> dict:
    return {**_bash(command), "cwd": str(cwd)}


@pytest.mark.parametrize(("marker", "is_dir"), IN_PROGRESS_MARKERS)
def test_git_add_allowed_during_rebase_conflict(
    hooks: HookRunner, tmp_path, marker: str, is_dir: bool
) -> None:
    repo = _repo(tmp_path, marker, is_dir)

    for command, cwd in (
        ("git add file", repo),
        ("git stage file", repo),
        (f"git -C {repo} add file", tmp_path),
    ):
        run = hooks.run_payload(PY_HOOK, _bash_in(command, cwd))
        assert_clean_run(run)
        assert run.decision == SILENT, (command, run.stdout)


def test_git_add_denied_when_no_rebase_in_progress(hooks: HookRunner, tmp_path) -> None:
    repo = _repo(tmp_path)

    for command, cwd in (("git add file", repo), (f"git -C {repo} add file", tmp_path)):
        run = hooks.run_payload(PY_HOOK, _bash_in(command, cwd))
        assert_clean_run(run)
        assert run.decision == DENY, (command, run.stdout)
        assert "wt step commit" in _reason(run)
