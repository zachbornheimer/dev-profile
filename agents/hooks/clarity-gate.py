#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Stop hook — block an unclear report and tell the agent how to rewrite it.

TypeSafe judges the final message. A clear failure of a calibrated rule blocks.
A middle score, a short status, or a TypeSafe outage allows the stop. The
reject cap ends the loop if the rewrite still fails.

Reads last_assistant_message (Claude Stop), final_response (Hermes pre_verify),
or assistant_response. pre_verify is the Hermes event that can continue the turn.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))

from completion_gate_escalation import escalate_block
from completion_gate_session_state import LoopGuard, RejectLedger
from hook_common import Clock, Decision, HookEvent, HookSettings, run_hook
from typesafe_location import TYPESAFE_CLI

HOOK_NAME = "clarity-gate"
END_TURN_REASON = "end_turn"
JUDGED_EVENTS = frozenset({"Stop"})
CLI_ENV = "HC_CLARITY_JUDGE_CLI"
TIMEOUT_ENV = "HC_CLARITY_JUDGE_TIMEOUT_SECS"
CAP_ENV = "HC_CLARITY_REJECT_CAP"
DEFAULT_TIMEOUT_SECS = 18.0
# One rewrite per request. Three blocks in a row cost six regenerations of
# the same message in one session (claude:2ed0c871) and the third never
# scored higher than the first; the second Stop ends the loop instead.
DEFAULT_CAP = 1
SOURCE_TYPESAFE = "typesafe"
ACTION_BLOCK = "block"


def _timeout() -> float:
    try:
        value = float(os.environ.get(TIMEOUT_ENV, ""))
    except ValueError:
        return DEFAULT_TIMEOUT_SECS
    return value if value > 0 else DEFAULT_TIMEOUT_SECS


def _cap() -> int:
    try:
        value = int(os.environ.get(CAP_ENV, ""))
    except ValueError:
        return DEFAULT_CAP
    return value if value > 0 else DEFAULT_CAP


def _extra(event: HookEvent) -> dict:
    extra = event.payload.get("extra")
    return extra if isinstance(extra, dict) else {}


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _message(event: HookEvent) -> str:
    extra = _extra(event)
    for key in (
        "last_assistant_message",
        "lastAssistantMessage",
        "final_response",
        "finalResponse",
        "assistant_response",
        "assistantResponse",
    ):
        text = _text(event.payload.get(key)) or _text(extra.get(key))
        if text:
            return text
    return ""


def _session_key(event: HookEvent) -> str:
    extra = _extra(event)
    return (
        event.session_id
        or _text(event.payload.get("task_id"))
        or _text(extra.get("task_id"))
        or _text(extra.get("turn_id"))
    )


def _ask(message: str) -> tuple[str, dict]:
    cli = Path(os.environ.get(CLI_ENV, "")) if os.environ.get(CLI_ENV) else TYPESAFE_CLI
    if not cli.is_file():
        return f"cli-missing:{cli}", {}
    try:
        done = subprocess.run(
            [sys.executable, str(cli), "judge-clarity"],
            input=json.dumps({"message": message}),
            capture_output=True,
            text=True,
            timeout=_timeout(),
            check=False,
        )
    except subprocess.TimeoutExpired:
        return f"timeout-{_timeout():g}s", {}
    except OSError as exc:
        return f"cli-error:{type(exc).__name__}", {}
    if done.returncode != 0:
        return f"cli-exit-{done.returncode}", {}
    try:
        verdict = json.loads(done.stdout)
    except ValueError:
        return "cli-output-not-json", {}
    if not isinstance(verdict, dict):
        return "cli-output-not-object", {}
    if verdict.get("source") != SOURCE_TYPESAFE:
        return f"typesafe-unavailable:{verdict.get('reason') or 'unknown'}", verdict
    return "", verdict


def decide(event: HookEvent) -> Decision | None:
    reason = event.field("reason", "reason")
    if reason and reason != END_TURN_REASON:
        return Decision.no_objection(f"non-end-turn-reason-{reason}")
    if event.event_name not in JUDGED_EVENTS:
        return Decision.no_objection(f"event-{event.event_name or 'missing'}")
    message = _message(event)
    if not message:
        return Decision.no_objection("no-message")

    fallback, verdict = _ask(message)
    if fallback:
        return Decision.no_objection(f"typesafe-unavailable-allow:{fallback}")
    if verdict.get("action") != ACTION_BLOCK:
        return Decision.no_objection("typesafe-allow")

    settings = HookSettings.from_env()
    session_key = _session_key(event)
    turn = event.field("turn_number", "turnNumber") or event.field("attempt", "attempt")
    ledger = (
        RejectLedger(settings.state_dir / f"clarity-reject-{session_key}.tsv")
        if session_key
        else None
    )
    guard = (
        LoopGuard(settings.state_dir / f"clarity-loop-{session_key}.txt")
        if session_key and turn
        else None
    )
    return escalate_block(
        str(verdict.get("reason") or "Rewrite the last message so it is clear."),
        turn,
        guard,
        ledger,
        _cap(),
        Clock.from_env(),
    )


if __name__ == "__main__":
    # Disabled for now: allow the stop immediately, no TypeSafe call. Remove this line to re-enable.
    sys.exit(0)
    run_hook(HOOK_NAME, decide)
