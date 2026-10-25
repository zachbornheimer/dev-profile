#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""PostToolUse (Agent matcher) — delivers the work-order verification that
work-order-verify.py (SubagentStop) already recorded to the ORCHESTRATOR.

Why this exists as its own hook on its own event: SubagentStop
hookSpecificOutput.additionalContext resumes the SUBAGENT, not the parent —
per the Claude Code hooks reference, "SubagentStop hooks ... keep the
subagent running ... To inject context into the parent session after a
subagent returns, use a PostToolUse hook on the Agent tool instead." This
hook is that PostToolUse-on-Agent hook. work-order-verify.py no longer
emits additionalContext at all (see its header) — this is the only place
the verification reaches the orchestrator.

Correlation: PostToolUse's tool_response carries `agentId` but no order_id
or transcript path. The subagent's own transcript lives at
"<parent-transcript-dir>/<parent-session-id>/subagents/agent-<agentId>.jsonl"
(documented SubagentStop example path) — reconstructed here from the
parent's own transcript_path, giving lib/work-order-report.py the
transcript it needs to re-find the order_id, exactly as
lib/work-order-verify.py does.

Fails OPEN on every edge case: missing uv, non-Agent tool, a
background/non-completed run, no agentId, an unreconstructable transcript
path, or any parse error → silent (None decision), no output.
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

HOOK_NAME = "work-order-report"
SELF_DIR = Path(__file__).resolve().parent
REPORT_SCRIPT = SELF_DIR / "lib" / "work-order-report.py"
REPORT_TIMEOUT_SECS = 60
COMPLETED_STATUS = "completed"
TRANSCRIPT_SUFFIX = ".jsonl"
POST_TOOL_USE = "PostToolUse"
REPORT_LOG_LABEL = "report"
NOT_APPLICABLE = "not applicable"


def _run_report(envelope: str) -> dict | None:
    try:
        proc = subprocess.run(
            [str(REPORT_SCRIPT)],
            input=envelope,
            capture_output=True,
            text=True,
            timeout=REPORT_TIMEOUT_SECS,
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


def _agent_transcript_path(event: HookEvent) -> str | None:
    transcript_path = event.field("transcript_path", "transcriptPath")
    if not transcript_path.endswith(TRANSCRIPT_SUFFIX):
        return None
    session_dir = transcript_path[: -len(TRANSCRIPT_SUFFIX)]
    agent_id = (
        event.payload.get("tool_response", {}).get("agentId")
        if isinstance(event.payload.get("tool_response"), dict)
        else None
    )
    agent_transcript_path = f"{session_dir}/subagents/agent-{agent_id}.jsonl"
    return agent_transcript_path if Path(agent_transcript_path).is_file() else None


def _format_context(result: dict) -> str:
    undeclared = result.get("undeclared_writes") or []
    if undeclared:
        scope_note = (
            "UNDECLARED WRITES outside allowed_writes: "
            + ", ".join(undeclared)
            + (
                " — either amend the order (work_order_amend: add_allowed_write + reason, validated "
                "the same way) or reject this result. "
            )
        )
    else:
        scope_note = "no undeclared writes. "
    acceptance = ", ".join(
        f"{item['id']}={'pass' if item.get('passed') else 'FAIL'}"
        for item in result.get("acceptance_results", [])
    )
    return (
        f"work-order-verify (order_id={result.get('order_id', '')}): "
        f"{scope_note}"
        f"Acceptance: {acceptance}. "
        "Relay these harness-run results as the evidence, not the worker's own claim."
    )


def decide(event: HookEvent) -> Decision | None:
    if event.tool_name != "Agent":
        return None
    if shutil.which("uv") is None or not os.access(REPORT_SCRIPT, os.X_OK):
        return None

    tool_response = event.payload.get("tool_response")
    if not isinstance(tool_response, dict) or tool_response.get("status") != COMPLETED_STATUS:
        return None

    agent_id = tool_response.get("agentId")
    if not agent_id:
        return None

    agent_transcript_path = _agent_transcript_path(event)
    if agent_transcript_path is None:
        return None

    state_orders_dir = HookSettings.from_env().state_dir / "work-orders"
    envelope = json.dumps(
        {
            "agent_transcript_path": agent_transcript_path,
            "state_orders_dir": str(state_orders_dir),
            "agent_id": agent_id,
        }
    )
    result = _run_report(envelope)
    if result is None:
        return None

    if result.get("applicable") is not True:
        return Decision.no_objection(f"agent_id={agent_id} {result.get('reason', NOT_APPLICABLE)}")

    order_id = result.get("order_id", "<absent>")
    if "error" in result:
        return Decision.no_objection(f"order_id={order_id} {result['error']}")

    undeclared_count = len(result.get("undeclared_writes") or [])
    failed_count = sum(
        1 for item in result.get("acceptance_results", []) if item.get("passed") is False
    )
    detail = f"order_id={order_id} agent_id={agent_id} undeclared={undeclared_count} acceptance_failed={failed_count}"
    return Decision.context(
        _format_context(result), POST_TOOL_USE, REPORT_LOG_LABEL, log_detail=detail
    )


if __name__ == "__main__":
    run_hook(HOOK_NAME, decide)
