#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
# PreToolUse (Bash matcher) — blocks unscoped whole-filesystem searches.
#
# Incident (2026-09-17): across 5+ different sessions (ninja-quoter,
# agentmux, eapp-system, mail-automation) agents ran `find /` or
# `bfs ... /` — rooted at bare "/" — to locate a directory/file by name.
# None of them ever finished: each burned 10-40% CPU continuously for
# 15 minutes to 21+ hours (Time Machine and network mounts included in the
# walk) until a human found and killed them by hand. Nothing timed them out
# or scoped them. This is a structural block, not another manual kill.
#
# Denies `find`/`bfs`/`fd` when a bare "/" token appears as a search-path
# argument (not as part of another flag's value). ALLOW_ROOT_SEARCH=1
# present as a literal env-assignment token, or set in the process env,
# bypasses the guard for the rare case a whole-disk search is intended.
#
# Fails OPEN on any parse error or unexpected input: a false block is more
# costly than a missed check.
import json
import re
import shlex
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))

from hook_common import run_fail_open

STDIN_TIMEOUT_SECS = 5
HOOKS_LOG = Path.home() / ".claude" / "hooks" / "state" / "hooks.log"
HOOK_NAME = "unscoped-find-guard"
SEARCH_COMMANDS = {"find", "bfs", "fd"}
CONTROL_OPERATORS = {"&&", "||", ";", "|"}
# Flags whose next token is that flag's value, not a search path — so a
# bare "/" immediately after one of these is not flagged.
VALUE_TAKING_FLAGS = {
    "-regextype",
    "-maxdepth",
    "-mindepth",
    "-type",
    "-name",
    "-iname",
    "-path",
    "-ipath",
    "-newer",
    "-size",
    "-printf",
    "-fprintf",
    "-S",
}
SCOPE_HINT = (
    "scope the search instead: a repo root or known parent directory, "
    "`fd`/`rg --files` with a bounded path, or the escape hatch "
    "ALLOW_ROOT_SEARCH=1 if a whole-disk search is genuinely intended"
)


def log(decision: str, detail: str) -> None:
    try:
        HOOKS_LOG.parent.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        with HOOKS_LOG.open("a") as f:
            f.write(f"{now}\t{HOOK_NAME}\t{decision}\t{detail}\n")
    except OSError:
        # log() is the logging path itself — nowhere left to report a
        # failure to write the log, so drop it rather than crash the guard.
        pass


def read_stdin_json() -> dict:
    try:
        import select

        if not select.select([sys.stdin], [], [], STDIN_TIMEOUT_SECS)[0]:
            return {}
        raw = sys.stdin.read()
        if not raw:
            return {}
        return json.loads(raw)
    except (OSError, ValueError):
        return {}


def tool_name(payload: dict) -> str:
    return payload.get("tool_name") or payload.get("toolName") or ""


def tool_input_field(payload: dict, key: str):
    tool_input = payload.get("tool_input") or payload.get("toolInput") or {}
    return tool_input.get(key)


def strip_quoted_heredoc_bodies(cmd: str) -> str:
    """Drops the BODY of every quoted heredoc (`<<'EOF' ... EOF` /
    `<<"EOF" ... EOF`) from a command, keeping the command line itself
    (redirect targets and all) so the deny rules below never mistake file
    CONTENT being written for command arguments — the same class of bug
    hc_strip_heredoc_bodies (hook-common.sh) exists to fix for the shell
    hooks. A quoted heredoc body is never shell-interpolated, so its text
    is exactly what ends up on disk; an UNQUOTED heredoc (`<<EOF`) still
    interpolates variables/command substitution from the invoking shell,
    so that body is left in place for the tokenizer to see.

    Handles `<<WORD`, `<<-WORD` with WORD wrapped in matching single or
    double quotes. A `<<-` body may indent its terminator with tabs, which
    is why the terminator comparison strips leading tabs.
    """
    delim_re = re.compile(r"""<<-?\s*(['"])([^'"]+)\1""")
    lines = cmd.splitlines(keepends=True)
    out = []
    in_body = False
    delim = ""
    for line in lines:
        if in_body:
            probe = line.rstrip("\n").lstrip("\t")
            if probe == delim or line.rstrip("\n") == delim:
                in_body = False
            continue
        out.append(line)
        match = delim_re.search(line)
        if match:
            delim = match.group(2)
            in_body = True
    return "".join(out)


def tokenize(cmd: str):
    try:
        lexer = shlex.shlex(cmd, posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        return list(lexer)
    except ValueError:
        return cmd.split()


def deny(reason: str) -> int:
    log("deny", reason)
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            }
        )
    )
    return 0


def allow(detail: str) -> int:
    log("allow", detail)
    return 0


def find_search_command_indices(tokens):
    return [i for i, tok in enumerate(tokens) if tok in SEARCH_COMMANDS]


def segment_end(tokens, start):
    """Index of the next control operator after `start`, or len(tokens)."""
    for i in range(start, len(tokens)):
        if tokens[i] in CONTROL_OPERATORS:
            return i
    return len(tokens)


def has_bare_root_arg(tokens, cmd_index, end):
    """True if a standalone '/' token appears as a search-path argument
    between cmd_index+1 and end, skipping values of flags that consume
    their next token."""
    i = cmd_index + 1
    while i < end:
        tok = tokens[i]
        if tok in VALUE_TAKING_FLAGS:
            i += 2  # skip the flag's value too
            continue
        if tok == "/":
            return True
        i += 1
    return False


def main() -> int:
    payload = read_stdin_json()
    if tool_name(payload) != "Bash":
        return 0

    cmd = tool_input_field(payload, "command")
    if not cmd:
        return 0

    tokens = tokenize(strip_quoted_heredoc_bodies(cmd))

    if "ALLOW_ROOT_SEARCH=1" in tokens:
        return allow("ALLOW_ROOT_SEARCH=1 escape hatch present")

    for idx in find_search_command_indices(tokens):
        end = segment_end(tokens, idx)
        if has_bare_root_arg(tokens, idx, end):
            searched_cmd = tokens[idx]
            return deny(
                f"Blocked: `{searched_cmd}` rooted at bare '/' walks the "
                f"whole filesystem (Time Machine and network mounts "
                f"included) and nothing times it out. Five+ of these ran "
                f"unnoticed for 15 minutes to 21+ hours before being "
                f"found and killed by hand — {SCOPE_HINT}."
            )

    return allow("no unscoped root search detected")


if __name__ == "__main__":
    run_fail_open(HOOK_NAME, main)
