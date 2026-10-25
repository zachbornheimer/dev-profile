#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""PostToolUse / Stop / SessionEnd — reap leftover ssh belonging to this
session (ZYS-732). The harness can return tool_result without reaping the
child process group; ssh then keeps running detached.

Only kills ssh clients whose process table line, or an ancestor's, carries
this session's id. Untagged ssh (user terminals, reverse tunnels, other
sessions) is left alone. -N / ControlMaster / sshd are never killed.
Fail-open, never blocks, always exit 0.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))

from hook_common import (
    Clock,
    HookEvent,
    HookLog,
    HookSettings,
    read_stdin,
    run_fail_open,
)
from ssh_session_reap_process import ProcessKiller, ProcessTable
from ssh_session_reap_targets import ANCESTOR_WALK_DEFAULT, select_reap_targets

HOOK_NAME = "ssh-session-reap"
# Session ids from hook stdin are UUIDs / grok ids. Shorter tokens are too
# easy to substring-match in an unrelated command line.
MIN_SESSION_ID_CHARS = 8
UNMATCHABLE_SESSION_ID = re.compile(r"[^A-Za-z0-9._-]")


def _self_pids() -> frozenset[str]:
    pids = {str(os.getpid())}
    ppid = os.environ.get("PPID")
    if ppid:
        pids.add(ppid)
    extra = os.environ.get("SSH_REAP_SELF_PIDS", "")
    pids.update(part.strip() for part in extra.split(",") if part.strip())
    return frozenset(pids)


def main() -> None:
    settings = HookSettings.from_env()
    log = HookLog(HOOK_NAME, settings, Clock.from_env())

    raw = read_stdin(settings.stdin_timeout_secs)
    if not raw:
        return
    event = HookEvent.parse(raw)
    if event is None:
        return

    session_id = event.field("session_id", "sessionId") or os.environ.get("GROK_SESSION_ID", "")
    if not session_id:
        return
    if UNMATCHABLE_SESSION_ID.search(session_id):
        log.record("allow", "session-id-not-matchable")
        return
    if len(session_id) < MIN_SESSION_ID_CHARS:
        log.record("allow", "session-id-too-short")
        return

    table = ProcessTable(os.environ.get("SSH_REAP_PS_FILE")).read()
    if not table:
        return

    targets = select_reap_targets(table, session_id, _self_pids(), ANCESTOR_WALK_DEFAULT)
    killer = ProcessKiller(os.environ.get("SSH_REAP_KILL_FILE"))
    for pid in targets:
        killer.terminate(int(pid))

    if targets:
        log.record("reaped", f"count={len(targets)} session={session_id}")
    else:
        log.record("allow", "no-session-ssh")


if __name__ == "__main__":
    run_fail_open(HOOK_NAME, main)
