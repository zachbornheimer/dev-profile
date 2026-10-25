#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""chezmoi-guard — refuse `chezmoi apply` when a live ~/.agents or ~/.claude
file is ahead of the chezmoi source. Apply of unre-added live work silently
reverts it (ZYS-755). After editing ~/.agents, run `chezmoi re-add ~/.agents`
first; workers run this script before apply.

Usage:
  chezmoi-guard.py --check   # CLI: exit 1 if any live-ahead path
  chezmoi-guard.py           # same when stdin is a TTY or empty
  (PreToolUse Bash stdin)    # deny only when the command is chezmoi apply
                             # and live is ahead

Unlike a plain run_hook hook, this script is also a CLI (--check) and must
read stdin once to decide which mode it's in, so it composes hook_common's
public pieces (read_stdin, emit, ShellCommand) under run_fail_open instead
of going through run_hook: the CLI keeps its exit status, and a crash in
either mode is logged fail-open and exits 0.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))

from chezmoi_drift import (
    DriftReportSource,
    command_is_chezmoi_apply,
    live_ahead_paths,
    print_to_stderr,
    refuse_message,
)
from hook_common import (
    Clock,
    Decision,
    HookEvent,
    HookLog,
    HookSettings,
    ShellCommand,
    emit,
    read_stdin,
    run_fail_open,
)

HOOK_NAME = "chezmoi-guard"
USAGE = f"usage: {HOOK_NAME}.py [--check]"
DRIFT_REPORT_UNREADABLE = "chezmoi-guard: could not read drift report"
DRIFT_REPORT_FAILED_DETAIL = "drift-report-failed"
STDIN_TIMEOUT_DETAIL = "cancelled (stdin-timeout)"


def _drift_source() -> DriftReportSource:
    return DriftReportSource(hooks_dir=Path(__file__).resolve().parent)


def cli_check() -> int:
    """``--check`` / interactive / non-hook-payload path: exit 1 if live is ahead."""
    try:
        paths = live_ahead_paths(_drift_source().read())
    except (OSError, RuntimeError):
        print_to_stderr(DRIFT_REPORT_UNREADABLE)
        return 1
    if paths:
        print_to_stderr(refuse_message(paths))
        return 1
    return 0


def hook_check(event: HookEvent) -> Decision | None:
    """None means stay silent (no log line) — parity with the .sh's bare `return 0`."""
    command = event.tool_input("command")
    if not command:
        return None
    parsed = ShellCommand.parse(command)
    if parsed is None or not command_is_chezmoi_apply(list(parsed.words)):
        return None
    try:
        paths = live_ahead_paths(_drift_source().read())
    except (OSError, RuntimeError):
        return Decision.no_objection(DRIFT_REPORT_FAILED_DETAIL)
    if not paths:
        return None
    return Decision.deny(refuse_message(paths))


def _looks_like_hook_payload(event: HookEvent) -> bool:
    return bool(event.tool_name or event.event_name)


def main(argv: list[str]) -> int:
    if argv and argv[0] in ("-h", "--help"):
        print(USAGE)
        return 0
    if argv and argv[0] == "--check":
        return cli_check()
    if argv:
        print_to_stderr(USAGE)
        return 2

    if sys.stdin.isatty():
        return cli_check()

    settings = HookSettings.from_env()
    log = HookLog(HOOK_NAME, settings, Clock.from_env())
    raw = read_stdin(settings.stdin_timeout_secs)
    if raw is None:
        log.record_fail_open(STDIN_TIMEOUT_DETAIL)
        return 0
    if not raw.strip():
        return cli_check()

    event = HookEvent.parse(raw)
    if event is None or not _looks_like_hook_payload(event):
        return cli_check()

    decision = hook_check(event)
    if decision is not None:
        emit(decision, log)
    return 0


if __name__ == "__main__":
    run_fail_open(HOOK_NAME, lambda: main(sys.argv[1:]))
