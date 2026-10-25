"""classify-ticket request and policy."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import answers
from constants import (
    MODEL,
    REASON_BELOW_CONFIDENCE,
    REASON_SELECTED,
    REASON_UNAVAILABLE,
    SOURCE_FALLBACK,
    SOURCE_TYPESAFE,
    TICKET_CONFIDENCE_FLOOR,
    TICKET_ISSUE_TYPES,
    TICKET_PRIORITIES,
    TICKET_PRIORITY_NONE,
    TICKET_PRIORITY_NUMBERS,
    TICKET_TYPE_BUG,
    TICKET_TYPE_CLOUD,
    TICKET_TYPE_FEATURE,
    TICKET_TYPE_IMPROVEMENT,
    TICKET_TYPE_OTHER,
    TICKET_TYPE_SPEC,
    TICKET_TYPE_UNKNOWN,
)

QUESTION_ISSUE_TYPE = "issue_type"
QUESTION_PRIORITY = "priority"
QUESTION_MAYBE_DUPLICATE = "maybe_duplicate"
ISSUE_TYPE_CRITERIA = {
    TICKET_TYPE_FEATURE: "New user-facing capability.",
    TICKET_TYPE_BUG: "Broken or off-spec behavior.",
    TICKET_TYPE_IMPROVEMENT: "Ownership, refactor, lint debt, or developer experience.",
    TICKET_TYPE_CLOUD: "Infra, CI, or platform work.",
    TICKET_TYPE_SPEC: "Design or ADR work without code yet.",
    TICKET_TYPE_OTHER: "None of the typed labels fit; do not invent a label.",
}
PRIORITY_CRITERIA = {
    "p1": "Urgent. True urgency only.",
    "p2": "High.",
    "p3": "Medium.",
    "p4": "Low. Never invent p0.",
}


@dataclass(frozen=True, slots=True)
class TicketResult:
    issue_type: str
    label: str
    priority: int
    maybe_duplicate: float
    source: str
    reason: str
    confidence: float
    usage: dict[str, Any]

    def as_json(self) -> dict[str, Any]:
        return {
            "issue_type": self.issue_type,
            "label": self.label,
            "priority": self.priority,
            "maybe_duplicate": self.maybe_duplicate,
            "source": self.source,
            "reason": self.reason,
            "confidence": self.confidence,
            "usage": self.usage,
        }


def fallback(reason: str = REASON_UNAVAILABLE) -> TicketResult:
    return TicketResult(
        issue_type=TICKET_TYPE_UNKNOWN,
        label="",
        priority=TICKET_PRIORITY_NONE,
        maybe_duplicate=0.0,
        source=SOURCE_FALLBACK,
        reason=reason,
        confidence=0.0,
        usage={},
    )


def load_state(raw: str) -> dict[str, Any]:
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise TypeError("classify-ticket stdin must be a JSON object")
    return {
        "title": answers.text(payload.get("title")),
        "body": answers.text(payload.get("body")),
        "available_labels": answers.texts(payload.get("available_labels")),
        "open_titles": answers.texts(payload.get("open_titles")),
    }


def build_request(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "model": MODEL,
        "state": state,
        "questions": {
            QUESTION_ISSUE_TYPE: {
                "type": "choice",
                "instructions": "What issue type is this ticket given `title` and `body`?",
                "criteria": dict(ISSUE_TYPE_CRITERIA),
            },
            QUESTION_PRIORITY: {
                "type": "choice",
                "instructions": "What Linear priority is this ticket? Never invent p0.",
                "criteria": dict(PRIORITY_CRITERIA),
            },
            QUESTION_MAYBE_DUPLICATE: {
                "type": "noul",
                "instructions": ("Is an entry in `open_titles` the same outcome as this ticket?"),
                "criteria": {
                    "true": "An open title is the same outcome; report that, do not pick an id.",
                    "false": "No open title is the same outcome.",
                },
            },
        },
    }


def label_for(issue_type: str, available_labels: list[str]) -> str:
    if issue_type == TICKET_TYPE_OTHER:
        return ""
    token = issue_type.lower()
    contains = ""
    for label in available_labels:
        lowered = label.lower()
        if lowered == token:
            return label
        if token in lowered and not contains:
            contains = label
    return contains


def decide(
    answers_by_id: dict[str, Any],
    state: dict[str, Any],
    usage: Any,
) -> TicketResult:
    issue_type, confidence = answers.choice(answers_by_id, QUESTION_ISSUE_TYPE)
    priority_choice, _priority_confidence = answers.choice(answers_by_id, QUESTION_PRIORITY)
    if issue_type not in TICKET_ISSUE_TYPES:
        raise ValueError("TypeSafe ticket issue_type outside the closed set")
    if priority_choice not in TICKET_PRIORITIES:
        raise ValueError("TypeSafe ticket priority outside the closed set")
    if confidence < TICKET_CONFIDENCE_FLOOR:
        return fallback(REASON_BELOW_CONFIDENCE)
    labels = state.get("available_labels") or []
    if not isinstance(labels, list):
        labels = []
    return TicketResult(
        issue_type=issue_type,
        label=label_for(issue_type, [str(item) for item in labels]),
        priority=TICKET_PRIORITY_NUMBERS[priority_choice],
        maybe_duplicate=answers.noul(answers_by_id, QUESTION_MAYBE_DUPLICATE),
        source=SOURCE_TYPESAFE,
        reason=REASON_SELECTED,
        confidence=confidence,
        usage=usage if isinstance(usage, dict) else {},
    )
