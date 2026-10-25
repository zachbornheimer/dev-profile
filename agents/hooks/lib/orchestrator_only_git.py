"""Denylist rules for a `git` invocation inside orchestrator-only.py.

Ported from orchestrator-only.sh's git_sub_and_args/git_group_deny_reason and
the merge/rebase/apply dirty-tree/history-rewrite prechecks. A match returns
a short description of the destructive pattern (see next_step module for how
that maps to a retry); no match returns None — this is a denylist, everything
else is allowed by omission.
"""

from __future__ import annotations

from dataclasses import dataclass

from hook_common import GIT, Git

GLOBAL_OPTIONS_WITH_ARG = ("-C", "-c", "--git-dir", "--work-tree", "--namespace")
FORCE_FLAGS = ("--force", "-f", "--force-with-lease")
CLEAN_FORCE_FLAG_CHARS = frozenset("fxd")
MERGE_ONLY_REPAIR_FLAGS = ("--abort", "--continue", "--quit")

# Prefixes returned by git_group_deny_reason for a caller-side git precheck
# that ran a read-only probe (as opposed to a bare argument match).
MERGE_PRECHECK_PREFIX = "MERGECHECK:"
REBASE_APPLY_PRECHECK_PREFIX = "PRECHECK:"


def skip_global_options(words: list[str]) -> list[str]:
    """Drops leading global options (-C <path>, --git-dir=..., -*), returning
    the subcommand and its own arguments."""
    index = 0
    total = len(words)
    while index < total:
        word = words[index]
        if word in GLOBAL_OPTIONS_WITH_ARG:
            index += 2 if index + 1 < total else 1
        elif word.startswith("-"):
            index += 1
        else:
            break
    return words[index:]


def dash_c_dir(raw_words: list[str]) -> str | None:
    """The path following a leading ``-C <path>``, or None when there isn't one."""
    index = 0
    total = len(raw_words)
    while index < total:
        word = raw_words[index]
        if word == "-C":
            return raw_words[index + 1] if index + 1 < total else None
        if word in GLOBAL_OPTIONS_WITH_ARG:
            index += 2 if index + 1 < total else 1
        elif word.startswith("-"):
            index += 1
        else:
            break
    return None


def _arg_has(needle: str, args: list[str]) -> bool:
    return needle in args


def git_ref_is_remote(repo_dir: str, ref: str, probe: Git = GIT) -> bool:
    """True when <ref>'s leading path segment names a configured remote."""
    if "/" not in ref:
        return False
    remote_name = ref.split("/", 1)[0]
    exit_code, stdout = probe.run(repo_dir, "remote")
    if exit_code != 0:
        return False
    return remote_name in stdout.splitlines()


def _is_repo(repo_dir: str, probe: Git) -> bool:
    exit_code, _ = probe.run(repo_dir, "rev-parse", "--is-inside-work-tree")
    return exit_code == 0


def _porcelain_dirty_files(repo_dir: str, probe: Git) -> list[str]:
    _exit_code, stdout = probe.run(repo_dir, "status", "--porcelain")
    return [line.split(maxsplit=2)[1] for line in stdout.splitlines() if line.strip()]


def merge_deny_reason(repo_dir: str, args: list[str], probe: Git = GIT) -> str | None:
    """Refuses a merge into a dirty tree, or one a read-only probe shows would conflict.

    --abort/--continue/--quit only repair an in-progress merge, never start
    one, so the probe doesn't apply to them.
    """
    if args and args[0] in MERGE_ONLY_REPAIR_FLAGS:
        return None
    if not _is_repo(repo_dir, probe):
        return None  # not a repo — fail open

    dirty = _porcelain_dirty_files(repo_dir, probe)
    if dirty:
        return f"git merge into a dirty tree (uncommitted/untracked: {' '.join(dirty)}) — commit or stash first, then retry the merge"

    target = next((arg for arg in reversed(args) if not arg.startswith("-")), None)
    if target is None:
        return None  # no target ref to probe — fail open

    exit_code, merge_base = probe.run(repo_dir, "merge-base", "HEAD", target)
    if exit_code != 0:
        return None
    merge_base = merge_base.strip()
    exit_code, tree = probe.run(repo_dir, "merge-tree", merge_base, "HEAD", target)
    if exit_code != 0:
        return None
    conflicts = sum(1 for line in tree.splitlines() if line.startswith("<<<<<<<"))
    if conflicts > 0:
        return f"git merge {target} would conflict — resolve it on a branch first (merge there, fix conflicts, then merge the resolved branch)"
    return None


def rebase_deny_reason(repo_dir: str, args: list[str], probe: Git = GIT) -> str | None:
    """Refuses --onto a remote ref outright, and rebasing a branch already pushed."""
    onto = None
    for previous, current in zip([None, *args], args):
        if previous == "--onto":
            onto = current
    if onto is not None and git_ref_is_remote(repo_dir, onto, probe):
        return f"git rebase --onto a remote ref ({onto}) — rewrites shared history; rebase onto a local branch instead"

    if not _is_repo(repo_dir, probe):
        return None  # not a repo — fail open
    exit_code, upstream = probe.run(
        repo_dir, "rev-parse", "--symbolic-full-name", "@{u}"
    )
    if exit_code != 0:
        return None  # no upstream — local-only, safe
    upstream = upstream.strip()
    exit_code, _ = probe.run(repo_dir, "merge-base", "--is-ancestor", "HEAD", "@{u}")
    if exit_code == 0:
        return None  # HEAD has unpushed commits ahead — safe
    return (
        f"git rebase on a branch already pushed to {upstream} — would rewrite shared history; "
        "fetch a fresh branch from upstream instead of rebasing published commits"
    )


def apply_deny_reason(repo_dir: str, args: list[str], probe: Git = GIT) -> str | None:
    """Refuses a mutating apply into a dirty tree; --check/--3way/-3 are exempt."""
    if _arg_has("--check", args) or _arg_has("--3way", args) or _arg_has("-3", args):
        return None
    if not _is_repo(repo_dir, probe):
        return None
    dirty = _porcelain_dirty_files(repo_dir, probe)
    if not dirty:
        return None
    return (
        f"git apply into a dirty tree (uncommitted/untracked: {' '.join(dirty)}) — "
        "git stash, then retry, or retry git apply --3way"
    )


def _clean_force_flag(arg: str) -> bool:
    return (
        arg.startswith("-")
        and 1 <= len(arg) - 1 <= 3
        and set(arg[1:]) <= CLEAN_FORCE_FLAG_CHARS
    )


@dataclass(frozen=True, slots=True)
class GitCommand:
    """A `git`-prefixed simple command: its raw words (after `git`), split
    into the subcommand and its own arguments once global options are gone."""

    raw: list[str]

    @property
    def sub_and_args(self) -> list[str]:
        return skip_global_options(self.raw)

    @property
    def sub(self) -> str:
        parts = self.sub_and_args
        return parts[0] if parts else ""

    @property
    def sub_args(self) -> list[str]:
        return self.sub_and_args[1:]

    def repo_dir(self, fallback_cwd: str) -> str:
        return dash_c_dir(self.raw) or fallback_cwd


def deny_reason(raw_words: list[str], cwd: str, probe: Git = GIT) -> str | None:
    """The matched destructive pattern's description, or None (allowed)."""
    command = GitCommand(raw_words)
    sub, args = command.sub, command.sub_args

    # --no-verify on ANY git subcommand (the bypass tripwire also covers
    # `commit` specifically; this is the general form).
    if _arg_has("--no-verify", args):
        return "git --no-verify"

    if sub == "push":
        if any(_arg_has(flag, args) for flag in FORCE_FLAGS):
            return "git push --force"
        if any(arg.startswith("+") for arg in args):
            return "git push +refspec"
        return None
    if sub == "reset":
        return "git reset --hard" if _arg_has("--hard", args) else None
    if sub == "merge":
        reason = merge_deny_reason(command.repo_dir(cwd), args, probe)
        return f"{MERGE_PRECHECK_PREFIX}{reason}" if reason else None
    if sub == "rebase":
        reason = rebase_deny_reason(command.repo_dir(cwd), args, probe)
        return f"{REBASE_APPLY_PRECHECK_PREFIX}{reason}" if reason else None
    if sub == "apply":
        reason = apply_deny_reason(command.repo_dir(cwd), args, probe)
        return f"{REBASE_APPLY_PRECHECK_PREFIX}{reason}" if reason else None
    if sub in ("checkout", "restore"):
        if _arg_has("--", args) or _arg_has(".", args):
            return f"git {sub} (discards working changes)"
        return None
    if sub == "clean":
        for arg in args:
            if arg == "--force":
                return "git clean --force"
            if _clean_force_flag(arg):
                return f"git clean {arg}"
        return None
    if sub == "branch":
        if _arg_has("-D", args) or (
            _arg_has("--delete", args) and _arg_has("--force", args)
        ):
            return "git branch -D"
        return None
    if sub == "stash":
        return f"git stash {args[0]}" if args and args[0] in ("drop", "clear") else None
    if sub == "filter-branch":
        return "git filter-branch"
    if sub == "filter-repo":
        return "git filter-repo"
    if sub == "update-ref":
        return "git update-ref -d" if _arg_has("-d", args) else None
    if sub == "reflog":
        return "git reflog expire" if args and args[0] == "expire" else None
    if sub == "gc":
        return "git gc --prune=now" if _arg_has("--prune=now", args) else None
    if sub == "worktree":
        if (
            args
            and args[0] == "remove"
            and any(_arg_has(flag, args[1:]) for flag in ("--force", "-f"))
        ):
            return "git worktree remove --force"
        return None
    return None
