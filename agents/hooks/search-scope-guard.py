#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""PreToolUse (Bash|Glob|Grep matcher) — search-scope guard.

Incident (2026-09): `find /Users/zbornheimer ...` and `grep -r` runs started
by agent sessions ran 35-95 minutes each and pushed this Mac's load average
past 600. Nothing timed them out or scoped them before this hook existed.

Three rules, in order:

1. `find` is always denied, in command position — including after `;`,
   `&&`, `||`, `|`, `$(`, a backtick, `xargs`, `sudo`, `timeout N`, `env
   ...`, `nice`, or as a full path (`/usr/bin/find`). Use `fd` instead.
2. `fd`/`rg`/`ag`/`ack`/`du`/`tree`/`ls -R` rooted at home or root
   (`~`, `$HOME`, the literal home directory, `/`, `/Users`, `/System`,
   `/Volumes`, `/private`, `/opt`, `/usr`) is always denied, whether or
   not it has a timeout — including when there's no path argument and the
   command's cwd is one of those roots.
3. The same commands rooted at a known-huge tree exactly one level below
   home (`~/Developer`, `~/Developer/<Org>`, `~/Dropbox`, `~/Library`,
   `~/Documents`, `~/Downloads`, `~/.cache`, `~/go`) must be wrapped in
   `timeout`/`gtimeout` <= 120 seconds. `grep -r`/`-R`/`--recursive`
   anywhere is denied outright — use `rg` instead.
4. The harness `Glob`/`Grep` tools obey rules 2 and 3 on their `path`
   argument (the pattern's own directory for an absolute or `~` Glob, the
   call's cwd when there is no path). A tool call has no `timeout` wrapper,
   so a known-huge root is denied outright: name a narrower directory, or
   run `timeout 120 fd/rg` through run_command.

Two layers, like gate-bypass-tripwire: shell WORDS (ShellCommand.segments,
which already splits `$( ... )` into its own segment) for the normal case,
and a small TEXT regex for the one thing word-splitting can't see — a
backtick command substitution, since shlex doesn't treat a backtick as a
separator. layout_extract's `strip_heredoc_bodies` (already written for
layout-guard) drops heredoc BODY lines first, so `find` written as file
content inside a heredoc is data, not a command.

Fails OPEN on any parse error or unexpected input: a false block is far
more costly than a missed check.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))

from hook_common import Decision, HookEvent, ShellCommand, run_hook
from layout_extract import strip_heredoc_bodies
from layout_paths import home_dir, normalize_path

HOOK_NAME = "search-scope-guard"

Segment = tuple[str, ...]

MAX_TIMEOUT_SECONDS = 120
WRAPPER_ENV_LIKE = {"sudo", "nice"}
WRAPPER_TIMEOUT = {"timeout", "gtimeout"}
# Flags that consume the next word as a value, so it is never mistaken for
# the wrapped command. Not exhaustive — this guard only needs to see past
# the wrapper to the real command, not fully parse xargs.
XARGS_VALUE_FLAGS = {"-I", "-n", "-P", "-L", "-s", "-d", "-a", "-E"}
# Commands whose first positional argument is a pattern/glob, not a path —
# a second positional (if present) is the search root.
PATTERN_FIRST_COMMANDS = {"fd", "rg", "ag", "ack"}
# Commands whose positional arguments are all search roots.
PATH_ONLY_COMMANDS = {"du", "tree"}
SCOPE_COMMANDS = PATTERN_FIRST_COMMANDS | PATH_ONLY_COMMANDS | {"ls"}
# Harness search tools whose arguments name a root. Lowercase is what omp and
# Grok emit; hook_common does not alias these, so raw_tool_name is the key.
SEARCH_TOOL_NAMES = frozenset({"Glob", "Grep", "glob", "grep"})
GLOB_META_RE = re.compile(r"[*?\[{]")

ENV_ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=.*$")
DURATION_RE = re.compile(r"^(\d+)(s|m|h|d)?$")
DURATION_UNIT_SECONDS = {"s": 1, "m": 60, "h": 3600, "d": 86400}
RECURSIVE_SHORT_FLAG_RE = re.compile(r"^-[a-zA-Z]*[rR][a-zA-Z]*$")
# A backtick command substitution glues onto the next word (shlex doesn't
# split on backtick), so `find` there never appears as its own token.
BACKTICK_FIND_RE = re.compile(r"`\s*(?:[^\s`'\"]*/)?find\b")
SINGLE_QUOTED_SPAN_RE = re.compile(r"'[^'\n]*'")
HOME_ALIAS_WORD = "${HOME}"
HOME_ENV_WORD = "$HOME"

FIND_DENY_REASON = (
    "This command runs `find`, which can walk unbounded across large or networked mounts with "
    "nothing timing it out. Use `fd` instead — for example `fd -g 'name' <dir>` or "
    "`fd -t f -e go <dir>`."
)
GREP_RECURSIVE_REASON = (
    "This command runs `grep` with -r/-R/--recursive. Use `rg` instead: `rg <pattern> <dir>` — "
    "it respects .gitignore and is 10-100x faster."
)
DENIED_ROOT_REASON = (
    "This `{cmd}` search is rooted at '{root}', which walks the whole home or system tree. "
    "Name a narrower directory instead — the repo root, `~/Developer/<Org>/<repo>`, or `~/.claude`."
)
TIMEOUT_REQUIRED_REASON = (
    "This `{cmd}` search is rooted at '{root}', a known-large tree. Wrap it in "
    f"`timeout {MAX_TIMEOUT_SECONDS} {{cmd}} ...` (or `gtimeout`), <= {MAX_TIMEOUT_SECONDS}s, so a "
    "runaway search can't hang the session."
)
HUGE_TREE_TOOL_REASON = (
    "This `{cmd}` tool call is rooted at '{root}', a known-large tree, and a tool call cannot "
    "be wrapped in `timeout`. Name a narrower directory (`~/Developer/<Org>/<repo>`), or run "
    f"`timeout {MAX_TIMEOUT_SECONDS} fd ...` / `rg ...` through run_command."
)


def backtick_find_reason(command: str) -> str | None:
    blanked = SINGLE_QUOTED_SPAN_RE.sub("''", command)
    return FIND_DENY_REASON if BACKTICK_FIND_RE.search(blanked) else None


def parse_duration_seconds(duration_word: str) -> int | None:
    match = DURATION_RE.match(duration_word)
    if not match:
        return None
    count, unit = match.groups()
    return int(count) * DURATION_UNIT_SECONDS[unit or "s"]


def resolve_command(segment: Segment) -> tuple[int, str | None, int | None]:
    """Peels env-assignments/sudo/nice/timeout/env/xargs wrappers off the front of a
    segment. Returns (index of the real command word, that word or None, a
    `timeout`/`gtimeout` duration in seconds if one wrapped the command)."""
    index, length = 0, len(segment)
    timeout_seconds: int | None = None
    while index < length:
        word = segment[index]
        if ENV_ASSIGNMENT_RE.match(word):
            index += 1
            continue
        if word in WRAPPER_ENV_LIKE:
            index += 1
            while index < length and segment[index].startswith("-"):
                index += 1
            continue
        if word in WRAPPER_TIMEOUT:
            index += 1
            while index < length and segment[index].startswith("-"):
                index += 1
            if index < length:
                timeout_seconds = parse_duration_seconds(segment[index])
                index += 1
            continue
        if word == "env":
            index += 1
            while index < length and (
                segment[index].startswith("-")
                or ENV_ASSIGNMENT_RE.match(segment[index])
            ):
                index += 1
            continue
        if word == "xargs":
            index += 1
            while index < length and segment[index].startswith("-"):
                flag = segment[index]
                index += 1
                if flag in XARGS_VALUE_FLAGS and index < length:
                    index += 1
            continue
        break
    command_word = segment[index] if index < length else None
    return index, command_word, timeout_seconds


def find_reason(segment: Segment) -> str | None:
    _, command_word, _ = resolve_command(segment)
    if command_word and command_word.rsplit("/", 1)[-1] == "find":
        return FIND_DENY_REASON
    return None


def has_recursive_flag(flags: Segment) -> bool:
    for flag in flags:
        if flag == "--recursive":
            return True
        if flag.startswith("--"):
            continue
        if RECURSIVE_SHORT_FLAG_RE.match(flag):
            return True
    return False


def grep_recursive_reason(segment: Segment) -> str | None:
    index, command_word, _ = resolve_command(segment)
    if command_word is None or command_word.rsplit("/", 1)[-1] != "grep":
        return None
    return GREP_RECURSIVE_REASON if has_recursive_flag(segment[index + 1 :]) else None


def positional_args(segment: Segment, start_index: int) -> list[str]:
    return [word for word in segment[start_index:] if not word.startswith("-")]


def search_paths(basename: str, args: list[str]) -> list[str]:
    if basename in PATTERN_FIRST_COMMANDS:
        return args[1:]
    return args


def normalize_root(root_word: str, home: str) -> str:
    if root_word == HOME_ALIAS_WORD:
        root_word = HOME_ENV_WORD
    normalized = normalize_path(root_word)
    if normalized != "/" and normalized.endswith("/"):
        normalized = normalized.rstrip("/")
    return normalized


def is_denied_root(normalized: str, home: str) -> bool:
    return normalized in {
        home,
        "/",
        "/System",
        "/Volumes",
        "/private",
        "/opt",
        "/usr",
        "/Users",
    }


def is_huge_tree_root(normalized: str, home: str) -> bool:
    exact_roots = {
        f"{home}/Developer",
        f"{home}/Dropbox",
        f"{home}/Library",
        f"{home}/Documents",
        f"{home}/Downloads",
        f"{home}/.cache",
        f"{home}/go",
    }
    if normalized in exact_roots:
        return True
    developer_prefix = f"{home}/Developer/"
    if normalized.startswith(developer_prefix):
        remainder = normalized[len(developer_prefix) :]
        return bool(remainder) and "/" not in remainder
    return False


def scope_reason(segment: Segment, cwd: str, home: str) -> str | None:
    index, command_word, timeout_seconds = resolve_command(segment)
    if command_word is None:
        return None
    basename = command_word.rsplit("/", 1)[-1]
    if basename not in SCOPE_COMMANDS:
        return None
    flags_and_args = segment[index + 1 :]
    if basename == "ls" and not has_recursive_flag(flags_and_args):
        return None

    args = positional_args(segment, index + 1)
    paths = search_paths(basename, args)
    root_word = paths[-1] if paths else cwd
    if not root_word:
        return None

    normalized_root = normalize_root(root_word, home)
    if is_denied_root(normalized_root, home):
        return DENIED_ROOT_REASON.format(cmd=basename, root=root_word)
    if is_huge_tree_root(normalized_root, home) and (
        timeout_seconds is None or timeout_seconds > MAX_TIMEOUT_SECONDS
    ):
        return TIMEOUT_REQUIRED_REASON.format(cmd=basename, root=root_word)
    return None


def glob_pattern_root(pattern: str) -> str:
    """The directory an absolute or home-rooted Glob pattern starts walking from."""
    if not pattern.startswith(("/", "~", "$HOME")):
        return ""
    head = GLOB_META_RE.split(pattern, 1)[0]
    return head.rsplit("/", 1)[0] or "/"


def search_tool_reason(event: HookEvent, cwd: str, home: str) -> str | None:
    tool = event.raw_tool_name
    root_word = (
        glob_pattern_root(event.tool_input("pattern")) if tool.lower() == "glob" else ""
    )
    root_word = root_word or event.tool_input("path") or cwd
    if not root_word:
        return None
    normalized_root = normalize_root(root_word, home)
    if not normalized_root.startswith("/") and cwd:
        normalized_root = os.path.normpath(os.path.join(cwd, normalized_root))
    if is_denied_root(normalized_root, home):
        return DENIED_ROOT_REASON.format(cmd=tool, root=root_word)
    if is_huge_tree_root(normalized_root, home):
        return HUGE_TREE_TOOL_REASON.format(cmd=tool, root=root_word)
    return None


def check_bash_command(command: str, cwd: str) -> str | None:
    inspectable = strip_heredoc_bodies(command)

    reason = backtick_find_reason(inspectable)
    if reason:
        return reason

    parsed = ShellCommand.parse(inspectable)
    if parsed is None:
        return None

    home = home_dir()
    for segment in parsed.segments():
        reason = (
            find_reason(segment)
            or grep_recursive_reason(segment)
            or scope_reason(segment, cwd, home)
        )
        if reason:
            return reason
    return None


def decide(event: HookEvent) -> Decision | None:
    if event.raw_tool_name in SEARCH_TOOL_NAMES:
        reason = search_tool_reason(event, event.field("cwd", "cwd"), home_dir())
        if reason:
            return Decision.deny(reason)
        return Decision.no_objection(f"{HOOK_NAME}:in-scope")
    if event.tool_name != "Bash":
        return None
    command = event.tool_input("command")
    if not command:
        return None
    reason = check_bash_command(command, event.field("cwd", "cwd"))
    if reason:
        return Decision.deny(reason)
    return Decision.no_objection(f"{HOOK_NAME}:in-scope")


if __name__ == "__main__":
    run_hook(HOOK_NAME, decide)
