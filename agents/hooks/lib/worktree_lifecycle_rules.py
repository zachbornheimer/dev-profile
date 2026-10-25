"""Which raw git/gh invocations Worktrunk (`wt`) owns, and what to run instead.

Worktrunk owns the branch+worktree lifecycle: create (`wt switch --create`),
move between (`wt switch`), integrate (`wt merge`, `wt step rebase`,
`wt sync` for stacks), record (`wt step commit`) and clean up (`wt remove`,
`wt step prune`). Doing those steps with raw git skips its path template,
its hooks (workz provisioning, copy-ignored) and its merge-state checks.
Everything else — fetch, pull, stash, amend, diff, log, restoring
files, first-time publish (`git push -u`) — stays plain git: wt has no verified equivalent for them.

A rule returns the deny reason for one argv, or None to allow.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Callable
from pathlib import Path

from orchestrator_only_git import dash_c_dir, skip_global_options

HELP_FLAGS = frozenset({"-h", "--help"})
CREATE = "Create the branch in its own worktree: `wt switch --create <branch>` (add `--base <ref>` to fork from a ref)."
SWITCH = "Move to that branch's worktree: `wt switch <branch>` (`^` = default branch, `-` = previous)."
REMOVE = "Remove the worktree and its merged branch: `wt remove <branch>` (`-D` for an unmerged branch)."
MERGE = "Integrate with `wt merge [target]` (squash + rebase + fast-forward + cleanup); to only update this branch, `wt step rebase`."
REBASE = "Rebase this branch onto its target with `wt step rebase`; for a stack of worktree branches use `wt sync`."
STACK = "Rebase stacked worktree branches in dependency order with `wt sync` (`--fetch`, `--push`, `--prune` as needed)."
PRUNE = (
    "Clean up merged or stale worktrees with `wt step prune` (or `wt sync --prune`)."
)
RELOCATE = "Move worktrees to the configured path with `wt step relocate`."
COMMIT = "Stage and commit with `wt step commit` (LLM-written message; `--stage tracked|none` limits what is staged, `--dry-run` previews)."
COMMIT_TRACKED = "Commit tracked changes with `wt step commit --stage tracked` (LLM-written message; `--dry-run` previews)."
PUSH = "Push the stack with `wt sync --push-only` (branches that already have an upstream); publish a new branch with `git push -u origin <branch>`."
NEW_BRANCH_PUSH_FLAGS = frozenset({"--set-upstream", "--delete", "--tags", "--dry-run"})  # first publish, deletion and previews have no `wt` equivalent
DRY_RUN_FLAGS = frozenset({"--dry-run"})
AMEND_FLAGS = frozenset({"--amend"})  # wt has no amend; the rewrite stays plain git
PR_CHECKOUT ="Check out a PR in its own worktree: `wt switch pr:<number>`."

WORKTREE_RULES = {"add": CREATE, "remove": REMOVE, "prune": PRUNE, "move": RELOCATE}
CHECKOUT_CREATE_FLAGS = frozenset({"-b", "-B", "--orphan"})
CHECKOUT_PATH_MODE_FLAGS = frozenset(
    {"--", "-p", "--patch", "--ours", "--theirs", "--pathspec-from-file"}
)
BRANCH_DELETE_FLAGS = frozenset({"-d", "-D", "--delete"})
BRANCH_COPY_FLAGS = frozenset({"-c", "-C", "--copy"})
BRANCH_NON_CREATING_FLAGS = frozenset({
    "-l", "--list", "-a", "--all", "-r", "--remotes", "-v", "-vv", "--verbose",
    "--merged", "--no-merged", "--contains", "--no-contains", "--points-at",
    "--show-current", "--format", "--sort", "--column", "--no-column",
    "-m", "-M", "--move", "-u", "--set-upstream-to", "--unset-upstream", "--edit-description",
})  # fmt: skip
IN_PROGRESS_FLAGS = frozenset(
    {"--abort", "--continue", "--quit", "--skip", "--edit-todo", "--show-current-patch"}
)


def _flag_names(args: list[str]) -> set[str]:
    return {arg.split("=", 1)[0] for arg in args if arg.startswith("-")}


def _positionals(args: list[str]) -> list[str]:
    return [arg for arg in args if not arg.startswith("-")]


def _worktree(args: list[str]) -> str | None:
    action = args[0] if args else ""
    return WORKTREE_RULES.get(action)


def _checkout(args: list[str]) -> str | None:
    flags = _flag_names(args)
    if flags & CHECKOUT_CREATE_FLAGS:
        return CREATE
    if (
        flags & CHECKOUT_PATH_MODE_FLAGS
        or "-" not in args
        and len(_positionals(args)) != 1
    ):
        return None
    return (
        SWITCH
        + " To restore files, use `git restore <path>` or `git checkout <ref> -- <path>`."
    )


def _switch(args: list[str]) -> str | None:
    return (
        CREATE
        if _flag_names(args) & {"-c", "-C", "--create", "--force-create", "--orphan"}
        else SWITCH
    )


def _branch(args: list[str]) -> str | None:
    flags = _flag_names(args)
    if flags & BRANCH_DELETE_FLAGS or _short_letters(args) & {"d", "D"}:
        return REMOVE
    if flags & BRANCH_NON_CREATING_FLAGS:
        return None
    if flags & BRANCH_COPY_FLAGS or _positionals(args):
        return CREATE
    return None


def _short_letters(args: list[str]) -> set[str]:
    return {
        char
        for arg in args
        if arg.startswith("-") and not arg.startswith("--")
        for char in arg[1:]
    }


IN_PROGRESS_MARKERS = (
    "rebase-merge",
    "rebase-apply",
    "MERGE_HEAD",
    "CHERRY_PICK_HEAD",
    "REVERT_HEAD",
)
GIT_DIR_TIMEOUT_SECONDS = 2
STAGING_COMMANDS = frozenset({"add", "stage"})


def operation_in_progress(repo_dir: str | None) -> bool:
    """True when the repo at `repo_dir` has a rebase, merge, cherry-pick or revert open.

    Marking a conflict resolved needs plain `git add`; Worktrunk has no verb
    for it. Any failure to find the git dir answers False here, and the caller
    allows staging then (fail open), so this never blocks on a git error.
    """
    try:
        out = subprocess.run(
            ["git", "-C", repo_dir or ".", "rev-parse", "--git-dir"],
            capture_output=True, text=True, timeout=GIT_DIR_TIMEOUT_SECONDS, check=True,
        ).stdout.strip()  # fmt: skip
        git_dir = Path(repo_dir or ".") / out
        return any((git_dir / marker).exists() for marker in IN_PROGRESS_MARKERS)
    except (OSError, subprocess.SubprocessError):
        return False


def _stage(args: list[str]) -> str | None:
    return None if _flag_names(args) & DRY_RUN_FLAGS else COMMIT


def _commit(args: list[str]) -> str | None:
    flags = _flag_names(args)
    if flags & (DRY_RUN_FLAGS | AMEND_FLAGS):
        return None
    if "--all" in flags or "a" in _short_letters(args):
        return COMMIT_TRACKED
    return COMMIT


def _push(args: list[str]) -> str | None:
    if _flag_names(args) & NEW_BRANCH_PUSH_FLAGS or _short_letters(args) & {"u", "d", "n"}:
        return None
    return PUSH


def _merge(args: list[str]) -> str | None:
    return None if _flag_names(args) & IN_PROGRESS_FLAGS else MERGE


def _rebase(args: list[str]) -> str | None:
    flags = _flag_names(args)
    if flags & IN_PROGRESS_FLAGS:
        return None
    return STACK if "--onto" in flags else REBASE


GIT_RULES: dict[str, Callable[[list[str]], str | None]] = {
    "worktree": _worktree,
    "checkout": _checkout,
    "switch": _switch,
    "branch": _branch,
    "merge": _merge,
    "rebase": _rebase,
    "add": _stage,
    "stage": _stage,
    "commit": _commit,
    "push": _push,
}


def _repo_dir(argv: list[str], cwd: str | None) -> str | None:
    """The directory git acts in: `-C <path>` (relative to cwd) else cwd."""
    target = dash_c_dir(argv[1:])
    if target is None:
        return cwd
    return os.path.join(cwd, target) if cwd else target


def _git_violation(argv: list[str], cwd: str | None = None) -> str | None:
    subcommand_and_args = skip_global_options(argv[1:])
    if not subcommand_and_args:
        return None
    subcommand, *args = subcommand_and_args
    rule = GIT_RULES.get(subcommand)
    if rule is None or HELP_FLAGS & set(args):
        return None
    violation = rule(args)
    if (
        violation
        and subcommand in STAGING_COMMANDS
        and operation_in_progress(os.path.expanduser(_repo_dir(argv, cwd) or "") or None)
    ):
        return None
    return violation


def _gh_violation(argv: list[str], cwd: str | None = None) -> str | None:
    return PR_CHECKOUT if argv[1:3] in (["pr", "checkout"], ["pr", "co"]) else None


PROGRAM_RULES: dict[str, Callable[[list[str], str | None], str | None]] = {
    "git": _git_violation,
    "gh": _gh_violation,
}


def lifecycle_violation(argv: list[str], cwd: str | None = None) -> str | None:
    """The `wt` replacement for a raw lifecycle command, or None when git owns it.

    `cwd` is the directory the command runs in; it locates the repository for
    `git add`/`git stage`, which stay plain git while a rebase/merge/cherry-pick
    is open (`rebase-merge` etc. under the git dir) so conflicts can be resolved.
    """
    rule = PROGRAM_RULES.get(os.path.basename(argv[0])) if argv else None
    return rule(argv, cwd) if rule else None
