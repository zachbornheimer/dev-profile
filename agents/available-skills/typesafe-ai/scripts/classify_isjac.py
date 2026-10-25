"""classify-isjac request and policy."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import answers
from constants import (
    ISJAC_CONFIDENCE_FLOOR,
    ISJAC_IN_SCOPE_FLOOR,
    ISJAC_KIND_NOISE,
    ISJAC_KIND_OPS_SKIP,
    ISJAC_KIND_PRODUCT_BUG,
    ISJAC_KIND_UNKNOWN,
    ISJAC_KINDS,
    MODEL,
    REASON_BELOW_CONFIDENCE,
    REASON_IN_SCOPE_BELOW_FLOOR,
    REASON_SELECTED,
    REASON_UNAVAILABLE,
    SOURCE_FALLBACK,
    SOURCE_TYPESAFE,
)

QUESTION_KIND = "kind"
QUESTION_IN_SCOPE = "in_scope"
STATE_FIELDS = ("subject", "from", "body")
KIND_CRITERIA = {
    ISJAC_KIND_PRODUCT_BUG: "A site or tech bug Zach should fix.",
    ISJAC_KIND_OPS_SKIP: "Ops, member-reply, or process work with no product ticket.",
    ISJAC_KIND_NOISE: (
        "Spam, security alerts, newsletters, Search Console, Clarity, or collab with no site bug."
    ),
}


@dataclass(frozen=True, slots=True)
class IsjacResult:
    kind: str
    confidence: float
    in_scope: float
    source: str
    reason: str
    usage: dict[str, Any]

    def as_json(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "confidence": self.confidence,
            "in_scope": self.in_scope,
            "source": self.source,
            "reason": self.reason,
            "usage": self.usage,
        }


def fallback(reason: str = REASON_UNAVAILABLE) -> IsjacResult:
    return IsjacResult(
        kind=ISJAC_KIND_UNKNOWN,
        confidence=0.0,
        in_scope=0.0,
        source=SOURCE_FALLBACK,
        reason=reason,
        usage={},
    )


def load_state(raw: str) -> dict[str, str]:
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise TypeError("classify-isjac stdin must be a JSON object")
    return {field: answers.text(payload.get(field)) for field in STATE_FIELDS}


def build_request(state: dict[str, str]) -> dict[str, Any]:
    return {
        "model": MODEL,
        "state": state,
        "questions": {
            QUESTION_KIND: {
                "type": "choice",
                "instructions": (
                    "What kind of ISJAC mail is this given `subject`, `from`, and `body`?"
                ),
                "criteria": dict(KIND_CRITERIA),
            },
            QUESTION_IN_SCOPE: {
                "type": "noul",
                "instructions": (
                    "Is this login, auth, membership, payment, cart, account, "
                    "form, embed, deploy, or security that blocks the site?"
                ),
                "criteria": {
                    "true": (
                        "The mail reports a site-blocking login, auth, membership, "
                        "payment, cart, account, form, embed, deploy, or security issue."
                    ),
                    "false": "The mail is not a site-blocking product or tech issue.",
                },
            },
        },
    }


def decide(
    answers_by_id: dict[str, Any],
    _state: dict[str, str],
    usage: Any,
) -> IsjacResult:
    kind, confidence = answers.choice(answers_by_id, QUESTION_KIND)
    in_scope = answers.noul(answers_by_id, QUESTION_IN_SCOPE)
    if kind not in ISJAC_KINDS:
        raise ValueError("TypeSafe isjac kind outside the closed set")
    if confidence < ISJAC_CONFIDENCE_FLOOR:
        return fallback(REASON_BELOW_CONFIDENCE)
    reason = REASON_SELECTED
    if kind == ISJAC_KIND_PRODUCT_BUG and in_scope < ISJAC_IN_SCOPE_FLOOR:
        kind = ISJAC_KIND_OPS_SKIP
        reason = REASON_IN_SCOPE_BELOW_FLOOR
    return IsjacResult(
        kind=kind,
        confidence=confidence,
        in_scope=in_scope,
        source=SOURCE_TYPESAFE,
        reason=reason,
        usage=usage if isinstance(usage, dict) else {},
    )
