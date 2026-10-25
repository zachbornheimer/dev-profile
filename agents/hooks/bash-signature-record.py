#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""PostToolUse + PostToolUseFailure (Bash matcher) — H4 (two-strikes-then-
diagnose). Records a normalized command signature and its outcome
(success/fail) into a per-session history file. PreToolUse consults this
history before letting a third identical-signature attempt run.

Which outcome to record is derived from hook_event_name: PostToolUse only
fires on success, PostToolUseFailure only on failure (confirmed in docs).

Never blocks (recording only) — always exits 0 (via run_hook, fail-open).
"""

from __future__ import annotations

import atexit
import contextlib
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))

from hook_common import (
    Clock,
    Decision,
    HookEvent,
    HookSettings,
    command_signature,
    run_hook,
)

HOOK_NAME = "bash-signature-record"
# hc_log's decision word for a successful recording (hook-common.sh parity).
RECORDED_LOG_LABEL = "recorded"
HISTORY_PRUNE_AGE_SECS = 86400
SSH_REAP_SCRIPT = Path(__file__).resolve().parent / "ssh-session-reap.py"
SSH_REAP_TIMEOUT_SECS = 5

OUTCOME_BY_EVENT = {
    "PostToolUse": "success",
    "PostToolUseFailure": "fail",
}


def _record_history(
    session_id: str, signature: str, outcome: str, clock: Clock, settings: HookSettings
) -> None:
    settings.state_dir.mkdir(parents=True, exist_ok=True)
    history = settings.state_dir / f"bash-history-{session_id}.tsv"
    now = int(clock.now_epoch())
    cutoff = now - HISTORY_PRUNE_AGE_SECS
    kept_lines: list[str] = []
    if history.exists():
        with contextlib.suppress(OSError):
            for line in history.read_text(encoding="utf-8", errors="replace").splitlines():
                timestamp_field = line.split("\t", 1)[0]
                try:
                    timestamp = int(timestamp_field)
                except ValueError:
                    continue
                if timestamp >= cutoff:
                    kept_lines.append(line)
    kept_lines.append(f"{now}\t{signature}\t{outcome}")
    with contextlib.suppress(OSError):
        history.write_text("\n".join(kept_lines) + "\n", encoding="utf-8")


def _reap_leftover_ssh(event: HookEvent) -> None:
    # ZYS-732: leftover ssh from this Bash tool must not outlive tool_result.
    # Fail-open: reap errors must not affect the signature record. The reap
    # script only reads session_id/sessionId, so the re-serialized payload
    # is equivalent to the original stdin bytes for its purposes.
    with contextlib.suppress(Exception):
        subprocess.run(
            [str(SSH_REAP_SCRIPT)],
            input=json.dumps(event.payload),
            capture_output=True,
            text=True,
            timeout=SSH_REAP_TIMEOUT_SECS,
            check=False,
        )


def decide(event: HookEvent) -> Decision | None:
    session_id = event.session_id
    command = event.tool_input("command")
    if not session_id or not command:
        return None

    outcome = OUTCOME_BY_EVENT.get(event.event_name)
    if outcome is None:
        return None

    signature = command_signature(command)
    if not signature:
        return None

    _record_history(session_id, signature, outcome, Clock.from_env(), HookSettings.from_env())
    # Reap after run_hook logs this decision (hook-common.sh parity: the
    # .sh's hc_log call for its own recording precedes the reap call, so
    # the reap's own log line always comes second). atexit fires after
    # run_hook's log.record but before process exit.
    atexit.register(_reap_leftover_ssh, event)
    return Decision.no_objection(f"{outcome}:{signature}", log_label=RECORDED_LOG_LABEL)


if __name__ == "__main__":
    run_hook(HOOK_NAME, decide)
