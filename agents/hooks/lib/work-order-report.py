#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Orchestrator-side half of the structured work-order protocol: delivers
the verification lib/work-order-verify.py already recorded (at
SubagentStop, keyed by order_id + agent_id in
state/work-orders/<order_id>.json) to the PARENT session.

Why this is a separate script from a separate hook, not more output from
work-order-verify.sh: SubagentStop hookSpecificOutput.additionalContext
resumes the SUBAGENT ("keeps the subagent running", per the Claude Code
hooks reference on SubagentStop decision control) — it never reaches the
orchestrator. A PostToolUse hook matched on the `Agent` tool call fires in
the PARENT's own turn, once, when that call completes; its
additionalContext lands in the parent's context instead. See
work-order-report.sh's header for the full citation.

Correlation: PostToolUse's `tool_response.agentId` names the subagent, but
gives no order_id (only work-order-verify.py's transcript-marker lookup
does, at SubagentStop). Rather than re-deriving order_id from tool_input
here, this script is handed the subagent's OWN transcript path (which
work-order-report.sh reconstructs from the parent's transcript_path +
agentId, per the documented `<session>/subagents/agent-<agent_id>.jsonl`
layout) and re-runs the same marker lookup work-order-verify.py uses — the
one thing both scripts are guaranteed to receive.

Entry point: reads a JSON envelope on stdin {"agent_transcript_path":...,
"state_orders_dir":..., "agent_id":...}, prints one JSON result object.
Idempotent: a second call for the same order_id + agent_id (e.g. Claude
Code re-firing a hook after a retry) reports `{"applicable": false,
"reason": "already reported"}` instead of re-emitting the same context —
"reported" is tracked separately from "verified" so a NEW report is never
skipped just because verification happened first.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ORDER_ID_RE = re.compile(r"work-order-id:\s*([0-9a-f]{64})")


def _message_text(message: dict) -> str:
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "\n".join(parts)
    return ""


def _find_order_id(transcript_path: Path) -> str | None:
    try:
        with transcript_path.open() as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if entry.get("type") != "user":
                    continue
                match = ORDER_ID_RE.search(_message_text(entry.get("message", {})))
                if match:
                    return match.group(1)
    except OSError:
        return None
    return None


def report() -> dict:
    envelope = json.loads(sys.stdin.read() or "{}")
    transcript_path_raw = envelope.get("agent_transcript_path") or ""
    state_orders_dir = Path(envelope.get("state_orders_dir") or "")
    agent_id = envelope.get("agent_id") or None

    if not transcript_path_raw:
        return {"applicable": False, "reason": "no agent_transcript_path"}
    order_id = _find_order_id(Path(transcript_path_raw))
    if not order_id:
        return {"applicable": False, "reason": "no work-order-id marker in agent transcript"}

    order_file = state_orders_dir / f"{order_id}.json"
    if not order_file.exists():
        return {"applicable": False, "reason": f"no state file for order_id={order_id}"}
    order_state = json.loads(order_file.read_text())

    verification = None
    for record in order_state.get("verifications", []):
        if not agent_id or record.get("agent_id") == agent_id:
            verification = record
            break
    if verification is None:
        return {"applicable": False, "reason": "no verification recorded yet for this agent"}

    reported_agent_ids = order_state.setdefault("reported_agent_ids", [])
    report_key = agent_id or f"order:{order_id}"
    if report_key in reported_agent_ids:
        return {"applicable": False, "reason": "already reported"}

    reported_agent_ids.append(report_key)
    order_file.write_text(json.dumps(order_state, indent=2, sort_keys=True))

    return {
        "applicable": True,
        "order_id": order_id,
        **verification,
    }


def main() -> int:
    print(json.dumps(report()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
