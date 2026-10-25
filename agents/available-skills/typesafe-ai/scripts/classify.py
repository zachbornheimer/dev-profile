"""classify-findings request and policy."""

from __future__ import annotations

import json
import re
from typing import Any

from constants import (
    ACTION_FALSE_POSITIVE,
    ACTION_FILE_NEW,
    ACTION_NO_CHANGE,
    ALWAYS_CLASSIFY_KINDS,
    CLASSIFY_SESSION_FLOOR,
    JOIN_PREFIX,
    MODEL,
    PRIMITIVES,
    SOURCE_FALLBACK,
    SOURCE_TYPESAFE,
)

QUESTION_ACTION = "action"
QUESTION_PRIMITIVE = "primitive"
TICKET_SANITIZE = re.compile(r"[^a-z0-9]+")

PRIMITIVE_CRITERIA = {
    "command": "No judgment; same argv every time.",
    "skill": "On-demand procedure the model must follow.",
    "hook": "Must fire even if the model forgets.",
    "subagent": "Raw output would wreck the parent.",
    "removal": "Fix or remove an existing instruction before adding another.",
    "none": "No primitive change.",
}


def should_classify(finding: dict[str, Any]) -> bool:
    kind = str(finding.get("kind") or "")
    if kind in ALWAYS_CLASSIFY_KINDS:
        return True
    try:
        return int(finding.get("session_count") or 0) >= CLASSIFY_SESSION_FLOOR
    except (TypeError, ValueError):
        return False


def sanitize_ticket_id(raw: str) -> str:
    return TICKET_SANITIZE.sub("_", raw.strip().lower()).strip("_")


def ticket_id(item: Any) -> str:
    if isinstance(item, str):
        first = item.split(None, 1)[0]
        return first.strip()
    if isinstance(item, dict):
        return str(item.get("id") or item.get("identifier") or "").strip()
    return ""


def ticket_title(item: Any) -> str:
    if isinstance(item, str):
        parts = item.split(None, 1)
        return parts[1] if len(parts) == 2 else item
    if isinstance(item, dict):
        return str(item.get("title") or item.get("name") or "")
    return ""


def action_key(raw_id: str) -> str:
    sanitized = sanitize_ticket_id(raw_id)
    return f"{JOIN_PREFIX}{sanitized}" if sanitized else ""


def canned_primitive(finding: dict[str, Any]) -> str:
    value = finding.get("proposed_primitive")
    if value in PRIMITIVES:
        return str(value)
    return "none"


def stamp_fallback(finding: dict[str, Any]) -> dict[str, Any]:
    out = dict(finding)
    out["typesafe_action"] = ACTION_NO_CHANGE
    out["typesafe_primitive"] = canned_primitive(finding)
    out["typesafe_source"] = SOURCE_FALLBACK
    return out


def load_payload(raw: str) -> tuple[list[dict[str, Any]], list[Any]]:
    if not raw.strip():
        return [], []
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("classify-findings stdin is not JSON") from exc
    if not isinstance(payload, dict):
        raise TypeError("classify-findings stdin must be a JSON object")
    findings = payload.get("findings") or []
    tickets = payload.get("tickets") or []
    if not isinstance(findings, list):
        raise TypeError("findings must be a list")
    if not isinstance(tickets, list):
        raise TypeError("tickets must be a list")
    return [item for item in findings if isinstance(item, dict)], list(tickets)


def build_request(finding: dict[str, Any], tickets: list[Any]) -> dict[str, Any]:
    criteria: dict[str, str] = {}
    for item in tickets:
        raw_id = ticket_id(item)
        key = action_key(raw_id)
        if not key:
            continue
        title = ticket_title(item)
        label = f"{raw_id}: {title}".strip() if title else raw_id
        criteria[key] = f"Join existing ticket {label}."
    criteria[ACTION_FILE_NEW] = "File a new Linear ticket; none of the open tickets cover this."
    criteria[ACTION_FALSE_POSITIVE] = "Drop as noise; not a real efficiency finding."
    criteria[ACTION_NO_CHANGE] = "Skip; already handled or no ticket needed."
    return {
        "model": MODEL,
        "state": {"finding": finding, "tickets": tickets},
        "questions": {
            QUESTION_ACTION: {
                "type": "choice",
                "instructions": (
                    "What should happen with this harness-efficiency finding "
                    "given the open tickets?"
                ),
                "criteria": criteria,
            },
            QUESTION_PRIMITIVE: {
                "type": "choice",
                "instructions": "Which durable primitive should the finding become?",
                "criteria": dict(PRIMITIVE_CRITERIA),
            },
        },
    }


def apply_answers(
    finding: dict[str, Any],
    answers: dict[str, Any],
    tickets: list[Any],
) -> dict[str, Any]:
    action_answer = answers.get(QUESTION_ACTION)
    primitive_answer = answers.get(QUESTION_PRIMITIVE)
    if not isinstance(action_answer, dict) or action_answer.get("type") != "choice":
        raise ValueError("TypeSafe answer action missing choice fields")
    if "choice" not in action_answer:
        raise ValueError("TypeSafe answer action missing choice")
    if not isinstance(primitive_answer, dict) or primitive_answer.get("type") != "choice":
        raise ValueError("TypeSafe answer primitive missing choice fields")
    if "choice" not in primitive_answer:
        raise ValueError("TypeSafe answer primitive missing choice")
    allowed_actions = {ACTION_FILE_NEW, ACTION_FALSE_POSITIVE, ACTION_NO_CHANGE}
    for item in tickets:
        key = action_key(ticket_id(item))
        if key:
            allowed_actions.add(key)
    action = str(action_answer["choice"])
    primitive = str(primitive_answer["choice"])
    if action not in allowed_actions or primitive not in PRIMITIVES:
        raise ValueError("TypeSafe classify choice outside the closed set")
    out = dict(finding)
    out["typesafe_action"] = action
    out["typesafe_primitive"] = primitive
    out["typesafe_source"] = SOURCE_TYPESAFE
    return out
