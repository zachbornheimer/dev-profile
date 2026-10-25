"""Hook entry points. Both guarantee fail-open: a crash never blocks the tool call.

- ``run_hook(name, decide)`` owns stdin, logging, and stdout for a hook
  that speaks the Claude Code decision protocol.
- ``run_fail_open(name, main)`` guards an entry point that owns its own
  protocol (a CLI mode, a WorktreeCreate path, a Cursor response shape).
"""

from __future__ import annotations

import os
import select
import signal
import sys
import time
from collections.abc import Callable
from typing import NoReturn

from .clock import Clock
from .decision import Decision
from .event import HookEvent
from .hook_log import HookLog
from .settings import HookSettings

STDIN_CHUNK_BYTES = 65536
# timeout(1)'s exit status on expiry — kept so the fail-open log line reads
# exactly like hook-common.sh's.
STDIN_TIMEOUT_STATUS = 124
STDIN_TIMEOUT_CAUSE = f"cancelled (stdin-timeout status={STDIN_TIMEOUT_STATUS})"


def read_stdin(timeout_secs: float) -> str | None:
    """All of stdin, or None if it isn't at EOF within the budget."""
    fd = sys.stdin.fileno()
    deadline = time.monotonic() + timeout_secs
    chunks: list[bytes] = []
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return None
        # select(), not a selectors/kqueue selector: kqueue never reports a
        # regular file (a redirected fixture) readable at EOF.
        ready, _, _ = select.select([fd], [], [], remaining)
        if not ready:
            return None
        chunk = os.read(fd, STDIN_CHUNK_BYTES)
        if not chunk:
            return b"".join(chunks).decode("utf-8", errors="replace")
        chunks.append(chunk)


def emit(decision: Decision, log: HookLog) -> None:
    """Log the decision, then print its JSON (if it has any)."""
    payload = decision.to_json()
    log.record(decision.log_label, decision.logged_detail)
    if payload is not None:
        sys.stdout.write(payload + "\n")
        sys.stdout.flush()


def _exit_on_cancel(log: HookLog) -> None:
    def handler(signum: int, _frame: object) -> None:
        log.record_fail_open(f"cancelled ({signal.Signals(signum).name})")
        os._exit(0)

    signal.signal(signal.SIGINT, handler)
    signal.signal(signal.SIGTERM, handler)


def _decide_and_emit(
    decide: Callable[[HookEvent], Decision | None], settings: HookSettings, log: HookLog
) -> None:
    raw = read_stdin(settings.stdin_timeout_secs)
    if raw is None:
        log.record_fail_open(STDIN_TIMEOUT_CAUSE)
        return
    event = HookEvent.parse(raw)
    if event is None:
        return
    decision = decide(event)
    if decision is not None:
        emit(decision, log)


def _hook_log(hook_name: str) -> HookLog:
    return HookLog(hook_name, HookSettings.from_env(), Clock.from_env())


def run_hook(hook_name: str, decide: Callable[[HookEvent], Decision | None]) -> NoReturn:
    """The entry point for a decision hook. Always exits 0.

    ``decide`` returns None to stay silent without logging, or a Decision.
    Any exception it raises is logged as fail-open and swallowed: a false
    block costs more than a missed check.
    """
    log = _hook_log(hook_name)
    _exit_on_cancel(log)
    try:
        _decide_and_emit(decide, HookSettings.from_env(), log)
    except Exception as exc:
        log.record_fail_open(f"{type(exc).__name__}: {exc}")
    sys.exit(0)


def run_fail_open(
    hook_name: str, main: Callable[[], int | None], fallback_output: str = ""
) -> NoReturn:
    """The entry point for a hook that owns its own protocol.

    ``main``'s return value is the exit status, so a CLI mode or a
    WorktreeCreate failure keeps its deliberate non-zero exit. An exception
    instead logs fail-open, prints ``fallback_output`` (the protocol's
    "no objection" response, e.g. ``{}`` for Cursor), and exits 0.
    """
    log = _hook_log(hook_name)
    _exit_on_cancel(log)
    try:
        status = main()
    except Exception as exc:
        log.record_fail_open(f"{type(exc).__name__}: {exc}")
        if fallback_output:
            sys.stdout.write(fallback_output + "\n")
            sys.stdout.flush()
        status = 0
    sys.exit(status or 0)
