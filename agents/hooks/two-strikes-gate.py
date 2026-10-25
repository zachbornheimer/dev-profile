#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""PreToolUse (Bash | Edit|Write | Agent|Task) — H4 (two-strikes-then-diagnose).

Bash: denies a call whose normalized signature matches the last two
consecutive FAILED entries in bash-history-<session>.tsv (written by
bash-signature-record.sh), with no success of that signature in between.
A success always resets the count.

Edit/Write: the same two-fail rule against edit-deny-history-<session>.tsv,
AND only when this session's edit-count is still empty (zero files
changed). Each allowed PreToolUse appends a fail so two other-gate
denials of the same path stop the third attempt. A later successful
edit (edit-record.sh) makes edit-count non-empty and this gate stays open.

Agent/Task inside a worker (agent_id present): the same two-fail +
zero-files rule against work-order-deny-history-<session>.tsv, keyed by
sha256 of the prompt. Orchestrator spawns (no agent_id) are not gated,
so fan-out of similar orders is not killed.

Worker/Edit two-fail + zero files is the ZYS-750 no-work kill: a worker
that hits the same denial twice without changing a file stops here.
Recurring identical denial is a harness defect (ZYS-736); this gate
names debug-protocol and refuses the third attempt. It does not
auto-file Linear — that would flood the tracker (original ZYS-750
Guard 2). File one ticket by hand if the gate itself is wrong.

Fails OPEN on any parse error, missing state, or unexpected input.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))

from hook_common import (
    Decision,
    HookEvent,
    HookSettings,
    command_signature,
    run_hook,
    sha256_digest,
)
from two_strikes_history import history_two_fails, record_fail, session_has_edits

HOOK_NAME = "two-strikes-gate"

# Zero-files Edit/Agent deny clause (ZYS-750): stop the worker; do not auto-file Linear.
NO_WORK_EXTRA = " with no file changed (ZYS-750 no-work kill; do not auto-file Linear)"
DENY_REASON = (
    "Two consecutive failures of this same approach (signature: '{sig}'){extra} — stop, "
    "load debug-protocol, diagnose the root cause before a third attempt. Recurring identical "
    "denial is a harness defect (see ZYS-736); do not retry the same call."
)


def _deny(signature: str, extra: str) -> Decision:
    """Logs just the signature, as the .sh's deny_two_strikes does."""
    return Decision.deny(DENY_REASON.format(sig=signature, extra=extra), log_detail=signature)


def _edit_file_path(event: HookEvent) -> str:
    for field in ("file_path", "path", "target_file"):
        value = event.tool_input(field)
        if value:
            return value
    return ""


def _decide_bash(event: HookEvent, state_dir: Path, session_id: str) -> Decision | None:
    command = event.tool_input("command")
    if not command:
        return None
    signature = command_signature(command)
    if not signature:
        return None
    history = state_dir / f"bash-history-{session_id}.tsv"
    if not history.is_file():
        return None
    if history_two_fails(history, signature):
        return _deny(signature, "")
    return Decision.no_objection(signature)


def _decide_edit(event: HookEvent, state_dir: Path, session_id: str) -> Decision | None:
    signature = _edit_file_path(event)
    if not signature:
        return None
    history = state_dir / f"edit-deny-history-{session_id}.tsv"
    if not session_has_edits(state_dir, session_id) and history_two_fails(history, signature):
        return _deny(signature, NO_WORK_EXTRA)
    record_fail(history, signature, int(time.time()))
    return Decision.no_objection(signature)


def _decide_agent(event: HookEvent, state_dir: Path, session_id: str) -> Decision | None:
    agent_id = event.field("agent_id", "agentId")
    if not agent_id:
        return None
    prompt = event.tool_input("prompt")
    if not prompt:
        return None
    signature = sha256_digest(prompt)
    if not signature:
        return None
    history = state_dir / f"work-order-deny-history-{session_id}.tsv"
    if not session_has_edits(state_dir, session_id) and history_two_fails(history, signature):
        return _deny(signature, NO_WORK_EXTRA)
    record_fail(history, signature, int(time.time()))
    return Decision.no_objection(signature)


def decide(event: HookEvent) -> Decision | None:
    session_id = event.session_id
    if not session_id:
        return None
    state_dir = HookSettings.from_env().state_dir
    match event.tool_name:
        case "Bash":
            return _decide_bash(event, state_dir, session_id)
        case "Edit" | "Write":
            return _decide_edit(event, state_dir, session_id)
        case "Agent" | "Task":
            return _decide_agent(event, state_dir, session_id)
        case _:
            return None


if __name__ == "__main__":
    run_hook(HOOK_NAME, decide)
