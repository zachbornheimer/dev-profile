#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""PreToolUse (Bash and Write|Edit matchers) — machine-layout guard.

Denies creating or writing into the agent-invented home folders that
~/.claude/rules/machine-layout.md forbids (~/work, ~/projects, ~/src, ...,
any *-LLC path segment), a git clone/init that targets ~/Desktop or the
home top-level, and a `git worktree add` whose destination isn't beside
its repo under a `.worktrees/` directory. Every denial names the
canonical destination so the caller can retry correctly on the first try.

Fails OPEN on any parse error or unexpected input: a false block is far
more costly than a missed check.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))

from hook_common import Decision, HookEvent, run_hook
from layout_extract import (
    git_subcommand_destination,
    last_positional_after,
    legacy_whitespace_tokenize,
    mkdir_targets,
    non_empty,
    redirection_targets,
    strip_heredoc_bodies,
    tokenize,
    worktree_add_destination,
)
from layout_paths import (
    CANONICAL_DESTINATION_HINT,
    destination_is_non_developer_home_direct,
    normalize_path,
    path_in_forbidden_location,
)

HOOK_NAME = "layout-guard"

FORBIDDEN_LOCATION_REASON = (
    "This command targets '{path}', a forbidden machine-layout location (an agent-invented "
    "home folder or a *-LLC path segment). " + CANONICAL_DESTINATION_HINT
)
FORBIDDEN_LOCATION_WRITE_REASON = (
    "This write targets '{path}', a forbidden machine-layout location (an agent-invented "
    "home folder or a *-LLC path segment). " + CANONICAL_DESTINATION_HINT
)
CLONE_HOME_REASON = (
    "git clone targets '{path}', a short-lived or non-project home location ($HOME top-level, "
    "~/Desktop, or ~/Dropbox) — never a project root. " + CANONICAL_DESTINATION_HINT
)
INIT_HOME_REASON = (
    "git init targets '{path}', a short-lived or non-project home location ($HOME top-level, "
    "~/Desktop, or ~/Dropbox) — never a project root. " + CANONICAL_DESTINATION_HINT
)
WORKTREE_OFF_CONVENTION_REASON = (
    "git worktree add's destination ('{path}') is not under a <repo-parent>/.worktrees/ "
    "directory. " + CANONICAL_DESTINATION_HINT
)

_GIT_CLONE_RE = re.compile(r"\bgit\b[ \t]+clone\b")
_GIT_INIT_RE = re.compile(r"\bgit\b[ \t]+init\b")
_GIT_WORKTREE_ADD_RE = re.compile(r"\bgit\b[ \t]+worktree[ \t]+add\b")


def _command_tokens(command: str) -> list[str]:
    inspectable = strip_heredoc_bodies(command)
    tokens = tokenize(inspectable)
    return tokens if tokens is not None else legacy_whitespace_tokenize(inspectable)


def check_bash_command(command: str) -> Decision | None:
    tokens = _command_tokens(command)
    # Heredoc bodies are file content (a commit message, a script), not commands.
    command = strip_heredoc_bodies(command)
    clone_dest = init_dest = worktree_dest = ""

    if _GIT_CLONE_RE.search(command):
        clone_dest = normalize_path(git_subcommand_destination(tokens, "clone", 2) or "")
        if destination_is_non_developer_home_direct(clone_dest):
            return Decision.deny(CLONE_HOME_REASON.format(path=clone_dest))

    if _GIT_INIT_RE.search(command):
        init_dest = normalize_path(git_subcommand_destination(tokens, "init", 1) or "")
        if destination_is_non_developer_home_direct(init_dest):
            return Decision.deny(INIT_HOME_REASON.format(path=init_dest))

    if _GIT_WORKTREE_ADD_RE.search(command):
        worktree_dest = normalize_path(worktree_add_destination(tokens) or "")
        if "/.worktrees/" not in worktree_dest:
            return Decision.deny(WORKTREE_OFF_CONVENTION_REASON.format(path=worktree_dest))

    targets = non_empty(
        [clone_dest, init_dest, worktree_dest]
        + mkdir_targets(tokens)
        + [last_positional_after(tokens, "cp"), last_positional_after(tokens, "mv")]
        + redirection_targets(tokens)
    )
    for target in targets:
        normalized = normalize_path(target)
        if path_in_forbidden_location(normalized):
            return Decision.deny(FORBIDDEN_LOCATION_REASON.format(path=normalized))
    return None


def check_write_edit(file_path: str) -> Decision | None:
    normalized = normalize_path(file_path)
    if path_in_forbidden_location(normalized):
        return Decision.deny(FORBIDDEN_LOCATION_WRITE_REASON.format(path=normalized))
    return None


def decide(event: HookEvent) -> Decision | None:
    tool_name = event.tool_name
    match tool_name:
        case "Bash":
            command = event.tool_input("command")
            if not command:
                return None
            return check_bash_command(command) or Decision.no_objection(
                f"{tool_name}:no-forbidden-location"
            )
        case "Write" | "Edit":
            file_path = event.tool_input("file_path")
            if not file_path:
                return None
            return check_write_edit(file_path) or Decision.no_objection(
                f"{tool_name}:no-forbidden-location"
            )
        case _:
            return None


if __name__ == "__main__":
    run_hook(HOOK_NAME, decide)
