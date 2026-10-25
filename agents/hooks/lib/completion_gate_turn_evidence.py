"""The envelope TypeSafe judges a Stop on: the final message, the request
that started the turn, and a compact digest of what tools actually did.

The digest carries facts, not text to pattern-match: this turn's tool
runs, subagent reports, and the ```evidence block's status. Every
field is capped so one huge tool result can't crowd out the rest.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from completion_gate_evidence import EvidenceClaim
from completion_gate_transcript import SHELL_TOOL, HistoryTurn, ToolRun, TranscriptFacts

# Guard against absurd input (pasted dumps); sized from measured lengths so normal turns are never cut (replies p99 ≈ 5.8k, prompts p95 ≈ 9.7k).
TEXT_SAFETY_CHARS = 10_000
COMMAND_CHARS = 200
COMMAND_OUTPUT_TAIL_CHARS = 600
REPORT_TAIL_CHARS = 500
COMMANDS_KEPT = 12
REPORTS_KEPT = 3
SUBAGENT_TOOLS = frozenset({"Agent", "Task"})
TRUNCATION_MARK = "…"


def _head(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit] + TRUNCATION_MARK


def _tail(text: str, limit: int) -> str:
    return text if len(text) <= limit else TRUNCATION_MARK + text[-limit:]


def _command_entry(run: ToolRun) -> dict[str, Any]:
    return {
        "command": _head(run.command, COMMAND_CHARS),
        "failed": run.failed,
        "output_tail": _tail(run.output.strip(), COMMAND_OUTPUT_TAIL_CHARS),
    }


def _evidence_block_status(claim: EvidenceClaim) -> dict[str, Any]:
    return {
        "present": claim.present,
        "valid": claim.shape_valid,
        "corroborated": claim.corroborated,
        "problem": claim.missing,
        "type": claim.claim_type,
        "ref": claim.ref,
    }


def build_digest(facts: TranscriptFacts | None, claim: EvidenceClaim) -> dict[str, Any]:
    runs = facts.turn_runs if facts is not None else ()
    commands = [run for run in runs if run.tool == SHELL_TOOL]
    reports = [run for run in runs if run.tool in SUBAGENT_TOOLS]
    return {
        "transcript_readable": facts is not None,
        "tool_counts_this_turn": dict(Counter(run.tool for run in runs)),
        "commands_this_turn": [
            _command_entry(run) for run in commands[-COMMANDS_KEPT:]
        ],
        "subagent_reports_this_turn": [
            _tail(run.output.strip(), REPORT_TAIL_CHARS)
            for run in reports[-REPORTS_KEPT:]
        ],
        "evidence_block": _evidence_block_status(claim),
    }


def _history_entry(turn: HistoryTurn) -> dict[str, str]:
    return {
        "user_request": _tail(turn.prompt, TEXT_SAFETY_CHARS),
        "response": _tail(turn.reply, TEXT_SAFETY_CHARS),
    }


def build_envelope(
    message: str, facts: TranscriptFacts | None, digest: dict[str, Any]
) -> dict[str, Any]:
    prompt = facts.user_prompt if facts is not None else ""
    return {
        "message": _tail(message.strip(), TEXT_SAFETY_CHARS),
        "user_prompt": _tail(prompt, TEXT_SAFETY_CHARS),
        "history": [_history_entry(turn) for turn in facts.history]
        if facts is not None
        else [],
        "evidence": digest,
    }
