"""Non-git denylist rules for one simple Bash command (gh, rm, sudo, kill,
chmod/chown, mise, npm), plus the dispatcher that also calls into git's.

Ported from orchestrator-only.sh's gh_group_deny_reason, rm_group_deny_reason,
chmod_chown_group_deny_reason, and group_deny_reason's non-git branches.
A match returns a short description of the destructive pattern; no match
returns None (allowed) — this is a denylist, everything else is allowed by
omission.
"""

from __future__ import annotations

import orchestrator_only_git as git_rules
from hook_common import GIT, Git
from orchestrator_only_paths import ScratchLocations, resolve_path

CHMOD_CHOWN_RECURSIVE_FLAGS = ("-R", "--recursive")
TRUNK_CACHE_MARKER = ".cache/trunk"


def _arg_has(needle: str, args: list[str]) -> bool:
    return needle in args


def gh_deny_reason(args: list[str]) -> str | None:
    """gh release create; gh pr merge --admin or --delete-branch on main."""
    c2 = args[0] if args else ""
    c3 = args[1] if len(args) > 1 else ""
    if c2 == "release":
        return "gh release create" if c3 == "create" else None
    if c2 == "pr" and c3 == "merge":
        merge_args = args[2:]
        if _arg_has("--admin", merge_args):
            return "gh pr merge --admin"
        if _arg_has("--delete-branch", merge_args) and _arg_has("main", merge_args):
            return "gh pr merge --delete-branch on main"
    return None


def _is_rm_recursive_flag(arg: str) -> bool:
    if arg == "--recursive":
        return True
    return arg.startswith("-") and not arg.startswith("--") and ("r" in arg[1:] or "R" in arg[1:])


def rm_deny_reason(args: list[str], cwd: str, scratch: ScratchLocations) -> str | None:
    """A recursive rm targeting anything outside the session scratchpad/$TMPDIR."""
    recursive = any(_is_rm_recursive_flag(arg) for arg in args)
    targets = [arg for arg in args if not arg.startswith("-")]
    if not recursive or not targets:
        return None
    for target in targets:
        if not scratch.contains(resolve_path(target, cwd)):
            return f"rm -r outside scratchpad/TMPDIR ({target})"
    return None


def _is_chmod_recursive_flag(arg: str) -> bool:
    if arg in ("-R", "--recursive"):
        return True
    return arg.startswith("-") and not arg.startswith("--") and "R" in arg[1:]


def chmod_chown_deny_reason(command: str, args: list[str], cwd: str, home: str) -> str | None:
    """A recursive chmod/chown targeting $HOME itself, not an arbitrary subdirectory."""
    recursive = any(_is_chmod_recursive_flag(arg) for arg in args)
    if not recursive:
        return None
    for arg in args:
        if arg.startswith("-"):
            continue
        resolved = resolve_path(arg, cwd)
        if resolved in (home, f"{home}/"):
            return f"{command} -R on $HOME"
    return None


def kill_deny_reason(command: str, args: list[str]) -> str | None:
    """kill/pkill -9, except when a target names the tamed trunk daemon cache."""
    if not _arg_has("-9", args):
        return None
    if any(TRUNK_CACHE_MARKER in arg for arg in args):
        return None
    return f"{command} -9"


def group_deny_reason(
    words: list[str],
    cwd: str,
    home: str,
    scratch: ScratchLocations,
    probe: Git = GIT,
) -> str | None:
    """The matched destructive pattern for one simple command's words, or None."""
    if not words:
        return None
    command, args = words[0], words[1:]
    c2 = args[0] if args else ""
    c3 = args[1] if len(args) > 1 else ""

    if command == "git":
        return git_rules.deny_reason(args, cwd, probe)
    if command in ("gh", "ghx"):
        return gh_deny_reason(args)
    if command == "rm":
        return rm_deny_reason(args, cwd, scratch)
    if command == "sudo":
        return "sudo"
    if command in ("kill", "pkill"):
        return kill_deny_reason(command, args)
    if command in ("chmod", "chown"):
        return chmod_chown_deny_reason(command, args, cwd, home)
    if command == "mise" and f"{c2} {c3}".startswith("run deploy"):
        return "mise run deploy*"
    if command == "npm" and c2 == "publish":
        return "npm publish"
    return None
