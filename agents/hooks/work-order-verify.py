#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""SubagentStop — work-order scope enforcement + harness-run acceptance.

Second half of the structured work-order protocol (see work-order-gate.py).
The gate validates and compiles an order at spawn time; this hook proves
what actually happened: it diffs the worker's worktree against the order's
declared `allowed_writes` and runs every `acceptance` command itself, so
the orchestrator relays a harness-run result, not a subagent's claim of
having stayed in scope or passed CI.

Correlation: PreToolUse fires before the subagent (and its agent_id) exist,
so the order_id can't be pre-mapped to agent_id at spawn time.
work-order-gate.py's compiled header embeds the order_id as a
transcript-visible marker instead; lib/work-order-verify.py reads it from
`agent_transcript_path` (present on SubagentStop input since Claude Code
2.0.42) — see that script's docstring for the full citation trail.

This hook NEVER returns SubagentStop hookSpecificOutput.additionalContext
(nor `decision: block`) — both "keep the subagent running" per the Claude
Code hooks reference. It only RECORDS the verification (via
lib/work-order-verify.py); work-order-report.py (PostToolUse on the Agent
tool call) is what surfaces the recorded report to the orchestrator.

Fails OPEN on every edge case: missing uv, a transcript with no
work-order-id marker (not every spawn is order-gated), a missing state
file, or any parse error → silent (None decision), no output.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))

from hook_common import Decision, HookEvent, HookSettings, run_hook

HOOK_NAME = "work-order-verify"
SELF_DIR = Path(__file__).resolve().parent
VERIFY_SCRIPT = SELF_DIR / "lib" / "work-order-verify.py"
VERIFY_TIMEOUT_SECS = 660
REPORT_LOG_LABEL = "report"
NOT_APPLICABLE = "not applicable"


def _run_verify(envelope: str) -> dict | None:
    try:
        proc = subprocess.run(
            [str(VERIFY_SCRIPT)],
            input=envelope,
            capture_output=True,
            text=True,
            timeout=VERIFY_TIMEOUT_SECS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    try:
        result = json.loads(proc.stdout)
    except ValueError:
        return None
    return result if isinstance(result, dict) else None


def decide(event: HookEvent) -> Decision | None:
    if shutil.which("uv") is None or not os.access(VERIFY_SCRIPT, os.X_OK):
        return None

    transcript_path = event.field("agent_transcript_path", "agentTranscriptPath")
    if not transcript_path:
        return None
    agent_id = event.field("agent_id", "agentId")

    state_orders_dir = HookSettings.from_env().state_dir / "work-orders"
    envelope = json.dumps(
        {
            "agent_transcript_path": transcript_path,
            "state_orders_dir": str(state_orders_dir),
            "agent_id": agent_id,
        }
    )
    result = _run_verify(envelope)
    if result is None:
        return None

    if result.get("applicable") is not True:
        return Decision.no_objection(result.get("reason") or NOT_APPLICABLE)

    order_id = result.get("order_id", "<absent>")
    if "error" in result:
        return Decision.no_objection(f"order_id={order_id} {result['error']}")

    undeclared_count = len(result.get("undeclared_writes") or [])
    failed_count = sum(
        1 for item in result.get("acceptance_results", []) if item.get("passed") is False
    )
    already = "true" if result.get("already_verified", False) else "false"
    detail = f"order_id={order_id} undeclared={undeclared_count} acceptance_failed={failed_count} already_verified={already}"
    return Decision.no_objection(detail, log_label=REPORT_LOG_LABEL)


if __name__ == "__main__":
    run_hook(HOOK_NAME, decide)
