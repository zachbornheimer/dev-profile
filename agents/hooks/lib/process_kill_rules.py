"""Which process-kill commands a worker may not run.

Two rules, both about killing by pattern:

1. Nothing may kill `wt` (worktrunk). A kill that lands mid `wt step commit`
   corrupts the in-flight signed commit and its hooks.
2. `pkill -f <pattern>` matches every command line containing the pattern,
   including other sessions' children, so it must go through `pkill-aged`,
   which only signals processes older than MIN_AGE_SECONDS.

`pkill-aged` itself is exempt from both: its age floor is the safeguard.
A deliberate override is `ALLOW_UNSAFE_PKILL=<reason>`.
"""

from __future__ import annotations

import os
import re

OVERRIDE_ENV = "ALLOW_UNSAFE_PKILL"
SAFE_WRAPPER = "pkill-aged"
MIN_AGE_SECONDS = 300
DISABLED_OVERRIDE_VALUES = frozenset({"", "0", "false", "no"})

OVERRIDE_ASSIGNMENT = re.compile(rf"(?:^|[\s;&|(]){OVERRIDE_ENV}=(\S*)")
# `wt` as a whole word. A preceding `/` is allowed (a binary path ends in
# /wt); a following `/` is not (that is a directory named wt).
WT_WORD = re.compile(r"(?<![\w.\-])(?:wt|worktrunk)(?![\w\-/])")
REGEX_WORD_ESCAPES = re.compile(r"\\[bBsSwWdD<>]")

PKILL_VALUE_FLAGS = frozenset({"-F", "-G", "-P", "-U", "-g", "-t", "-u", "-d", "-O"})
PKILL_PARENT_FLAG = "-P"
KILL_COMMANDS = frozenset({"kill"})
PID_SELECTORS = frozenset({"pgrep", "pidof", "grep", "egrep", "rg", "awk"})
FIRST_POSITIONAL_ONLY = frozenset({"grep", "egrep", "rg", "awk"})
COMMAND_PREFIXES = frozenset({"nice", "timeout", "gtimeout", "xargs"})
PREFIX_VALUE_FLAGS = {
    "xargs": frozenset({"-I", "-n", "-P", "-L", "-s", "-d", "-a", "-E"}),
    "nice": frozenset({"-n"}),
}
DURATION_PREFIXES = frozenset({"timeout", "gtimeout"})

WT_REASON = (
    "{command} would kill `wt` (worktrunk), and a kill mid `wt step commit` corrupts the "
    "in-flight signed commit and its hooks. Next: wait for the commit to finish. If a wt "
    f"process is truly stuck, run `{SAFE_WRAPPER} -f '<pattern>'` (only signals processes older "
    f"than {MIN_AGE_SECONDS}s). To override on purpose, prefix the command with "
    f"{OVERRIDE_ENV}='<reason>'."
)
BROAD_REASON = (
    "{command} matches every process whose command line contains the pattern, with no age "
    "limit, so it can kill other sessions' work. Next: use "
    f"`{SAFE_WRAPPER} -f '<pattern>'` (only signals processes older than {MIN_AGE_SECONDS}s; "
    "macOS pkill has no -O flag, which is why this wrapper exists) or scope to your own "
    "children with `pkill -P $$ ...`. To override on purpose, prefix the command with "
    f"{OVERRIDE_ENV}='<reason>'."
)


def override_active(command_text: str) -> bool:
    """True when the override was set deliberately: non-empty and not a disable word."""
    values = [match.group(1) for match in OVERRIDE_ASSIGNMENT.finditer(command_text)]
    values.append(os.environ.get(OVERRIDE_ENV, ""))
    return any(
        value.strip().lower() not in DISABLED_OVERRIDE_VALUES for value in values
    )


def targets_wt(pattern: str) -> bool:
    return bool(WT_WORD.search(REGEX_WORD_ESCAPES.sub(" ", pattern)))


def _skip_flag_values(words: list[str], value_flags: frozenset[str]) -> list[str]:
    """Positional words: everything that is not a flag or a flag's value."""
    positional: list[str] = []
    skip_next = False
    for word in words:
        if skip_next:
            skip_next = False
        elif word in value_flags:
            skip_next = True
        elif not word.startswith("-"):
            positional.append(word)
    return positional


def peel_command_prefixes(argv: list[str]) -> tuple[list[str], bool]:
    """Drops nice/timeout/xargs from the front; reports whether xargs fed the command.

    Public because the wrapper set is the same fact for every rule that asks "what does this
    command actually run": the scope guard's host-mutation test reuses it.
    """
    fed_by_xargs = False
    while argv and os.path.basename(argv[0]) in COMMAND_PREFIXES:
        prefix = os.path.basename(argv[0])
        fed_by_xargs = fed_by_xargs or prefix == "xargs"
        value_flags = PREFIX_VALUE_FLAGS.get(prefix, frozenset())
        index = 1
        while index < len(argv) and argv[index].startswith("-"):
            index += 2 if argv[index] in value_flags else 1
        if prefix in DURATION_PREFIXES and index < len(argv):
            index += 1
        argv = argv[index:]
    return argv, fed_by_xargs


def _has_pattern_flag(flags: list[str]) -> bool:
    """`-f` standing alone or inside a cluster like -fx; never inside a -SIGNAL name."""
    return any(
        flag.startswith("-")
        and not flag.startswith("--")
        and flag[1:].islower()
        and "f" in flag
        for flag in flags
    )


def _pkill_reason(args: list[str]) -> str | None:
    patterns = _skip_flag_values(args, PKILL_VALUE_FLAGS)
    if any(targets_wt(pattern) for pattern in patterns):
        return WT_REASON.format(command="pkill")
    scoped_to_parent = PKILL_PARENT_FLAG in args
    if _has_pattern_flag(args) and not scoped_to_parent:
        return BROAD_REASON.format(command="pkill -f")
    return None


def _killall_reason(args: list[str]) -> str | None:
    if any(
        targets_wt(name)
        for name in _skip_flag_values(args, frozenset({"-s", "-u", "-t", "-y", "-o"}))
    ):
        return WT_REASON.format(command="killall")
    return None


PROGRAM_RULES = {"pkill": _pkill_reason, "killall": _killall_reason}


def _selects_wt(program: str, args: list[str]) -> bool:
    patterns = _skip_flag_values(args, frozenset())
    if program in FIRST_POSITIONAL_ONLY:
        patterns = patterns[:1]
    return any(targets_wt(pattern) for pattern in patterns)


def _piped_kill_reason(commands: list[list[str]]) -> str | None:
    """A wt-selecting pgrep/grep feeding a `kill` (xargs kill, kill $(pgrep ...))."""
    selects_wt = False
    kills = False
    for argv in commands:
        peeled, _ = peel_command_prefixes(argv)
        if not peeled:
            continue
        program = os.path.basename(peeled[0])
        kills = kills or program in KILL_COMMANDS
        selects_wt = selects_wt or (
            program in PID_SELECTORS and _selects_wt(program, peeled[1:])
        )
    return (
        WT_REASON.format(command="kill of a wt process list")
        if kills and selects_wt
        else None
    )


def deny_reason(commands: list[list[str]], command_text: str) -> str | None:
    """The reason to deny these simple commands, or None when allowed."""
    if override_active(command_text):
        return None
    for argv in commands:
        peeled, _ = peel_command_prefixes(argv)
        if not peeled:
            continue
        program, args = os.path.basename(peeled[0]), peeled[1:]
        rule = PROGRAM_RULES.get(program)
        reason = rule(args) if rule else None
        if reason:
            return reason
    return _piped_kill_reason(commands)
