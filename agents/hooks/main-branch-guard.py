#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///

"""PreToolUse: no agent writes to `main`/`master` directly. Work in a worktree.

Rules, every repository:

- A state-mutating git command (`commit`, `merge`, `cherry-pick`, `rebase`,
  `am`, `revert`, `reset --hard`) while HEAD is `main`/`master` is denied. That
  covers a worktree somebody checked out on `main`: writing the default branch
  is what is being prevented, not merely writing it from the primary checkout.
- A push whose destination ref is `main`/`master` is denied from anywhere.
- Completing or abandoning an operation already in progress (`--abort`,
  `--continue`, `--quit`, `--skip`) stays allowed: that is recovery.
- `wt merge` / `wt land` are allowed (that is how a worktree branch lands).

oh-my-pi is stricter, because its `main` is a read-only mirror of
can1357/oh-my-pi: `wt merge` and `wt land` are denied there too.

Fails OPEN on parse errors, a missing git, or unexpected input, like every
guard here: a false block costs more than a missed check.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))

from command_words import simple_commands
from hook_common import Decision, HookEvent, run_hook
from orchestrator_only_git import dash_c_dir, skip_global_options

HOOK_NAME = "main-branch-guard"

PROTECTED_BRANCHES = frozenset({"main", "master"})
MUTATING_SUBCOMMANDS = frozenset(
    {"commit", "merge", "cherry-pick", "rebase", "am", "revert", "reset"}
)
IN_PROGRESS_FLAGS = frozenset({"--abort", "--continue", "--quit", "--skip"})
RESET_MUTATING_FLAGS = frozenset({"--hard", "--merge", "--keep"})
WT_SUBCOMMANDS = frozenset({"merge", "land"})
GIT_TIMEOUT_SECONDS = 2
# The same explicit overrides the git-level guards honour:
# dev-profile-no-commit-to-default-branch reads ..._COMMIT, and
# dev-profile-pre-push reads ..._PUSH. They exist for the human working in the
# profile checkout, where main is the live branch; documented, not hidden.
ALLOW_ENVS = (
    "DEV_PROFILE_ALLOW_DEFAULT_BRANCH_COMMIT",
    "DEV_PROFILE_ALLOW_DEFAULT_BRANCH_PUSH",
)
PUSH_OPTIONS_WITH_ARG = frozenset(
    {"-o", "--push-option", "--repo", "--receive-pack", "--exec"}
)

WORKTRUNK_FLOW = (
    "Work in a worktree instead: `wt switch --create <branch> --base origin/main`, "
    "then `wt step commit`; land with `wt land` or open a PR with `wt pr`."
)
OH_MY_PI_FLOW = (
    "oh-my-pi's `main` is a read-only mirror of can1357/oh-my-pi. Create a topic "
    "branch off origin/main (`wt switch --create <branch> --base origin/main`), "
    "push it to `fork`, and list it in the fork's `.github/omp-rebuild.toml` on "
    "the `ci` branch so CI builds the next release."
)


def extract_command(event: HookEvent) -> str:
    """The shell string, whether it arrives directly or nested in a
    `write xd://…run_command` bridge payload (omp's calling convention)."""
    cmd = event.tool_input("command")
    if cmd.strip():
        return cmd
    path = event.tool_input("path")
    content = event.tool_input("content")
    if "run_command" in path and content:
        try:
            parsed = json.loads(content)
        except ValueError:
            return ""
        if isinstance(parsed, dict) and isinstance(parsed.get("command"), str):
            return parsed["command"]
    return ""


def _git(repo: str, *args: str) -> str:
    """Stripped stdout on success, "" on any failure."""
    try:
        done = subprocess.run(
            ["git", "-C", repo, *args],
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return done.stdout.strip() if done.returncode == 0 else ""


def _inside_repo(repo: str) -> bool:
    return bool(_git(repo, "rev-parse", "--is-inside-work-tree"))


def _repo_name(repo: str) -> str:
    """The repository's own directory name, shared by all of its worktrees."""
    common_dir = _git(repo, "rev-parse", "--git-common-dir")
    if not common_dir:
        return ""
    if not os.path.isabs(common_dir):
        common_dir = os.path.join(repo, common_dir)
    return os.path.basename(os.path.dirname(os.path.normpath(common_dir)))


def _current_branch(repo: str) -> str:
    return _git(repo, "symbolic-ref", "--short", "-q", "HEAD")


def _git_subcommand(argv: list[str]) -> tuple[str, list[str]]:
    """(subcommand, its args) for a `git` argv, global options removed."""
    rest = skip_global_options(argv[1:])
    return (rest[0], rest[1:]) if rest else ("", [])


def _has_flag(args: list[str], flags: frozenset[str]) -> bool:
    return any(arg.split("=", 1)[0] in flags for arg in args)


def push_targets_default_branch(args: list[str], branch: str) -> bool:
    """True when a push's refspecs (or its implicit current branch) write main."""
    positionals: list[str] = []
    skip_next = False
    for arg in args:
        if skip_next:
            skip_next = False
            continue
        if arg in PUSH_OPTIONS_WITH_ARG:
            skip_next = True
            continue
        if arg.startswith("-"):
            continue
        positionals.append(arg)

    # positionals[0] is the remote when present; the rest are refspecs.
    refspecs = positionals[1:] if positionals else []
    if not refspecs:
        return branch in PROTECTED_BRANCHES
    for refspec in refspecs:
        refspec = refspec.lstrip("+")
        destination = refspec.split(":", 1)[1] if ":" in refspec else refspec
        destination = destination.strip()
        if destination == "HEAD":
            destination = branch
        destination = destination.removeprefix("refs/heads/")
        if destination in PROTECTED_BRANCHES:
            return True
    return False


def _deny(shown: str, flow: str, detail: str) -> Decision:
    return Decision.deny(
        f"`{shown}` writes to the default branch, which agents must not do "
        f"directly. {flow}",
        log_detail=detail,
    )


def decide(event: HookEvent) -> Decision | None:
    if event.tool_name not in {"Bash", "Write"}:
        return None
    command = extract_command(event)
    if not command:
        return None
    if any(os.environ.get(name) or f"{name}=" in command for name in ALLOW_ENVS):
        return None

    cwd = event.field("cwd", "cwd") or os.getcwd()
    for argv in simple_commands(command):
        shown = " ".join(argv)
        if argv[0] == "cd" and len(argv) == 2:
            cwd = argv[1]
            continue
        if argv[0] not in {"git", "wt"}:
            continue

        repo = os.path.expanduser(dash_c_dir(argv[1:]) or cwd)
        if not os.path.isdir(repo) or not _inside_repo(repo):
            continue
        branch = _current_branch(repo)
        in_oh_my_pi = _repo_name(repo) == "oh-my-pi"
        flow = OH_MY_PI_FLOW if in_oh_my_pi else WORKTRUNK_FLOW

        if argv[0] == "wt":
            wt_args = skip_global_options(argv[1:])
            sub = wt_args[0] if wt_args else ""
            if sub in WT_SUBCOMMANDS and in_oh_my_pi:
                if "omp-build" not in " ".join(wt_args[1:]):
                    return _deny(shown, OH_MY_PI_FLOW, "omp-wt-merge-main")
            continue

        sub, args = _git_subcommand(argv)
        if sub == "push":
            if push_targets_default_branch(args, branch):
                return _deny(shown, flow, "push-main")
            continue
        if sub not in MUTATING_SUBCOMMANDS:
            continue
        if branch not in PROTECTED_BRANCHES:
            continue
        if _has_flag(args, IN_PROGRESS_FLAGS):
            continue
        if sub == "reset" and not _has_flag(args, RESET_MUTATING_FLAGS):
            continue
        return _deny(shown, flow, f"{sub}-main")

    return None


if __name__ == "__main__":
    run_hook(HOOK_NAME, decide)
