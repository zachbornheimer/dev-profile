"""classify-oncall request and policy."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import answers
from constants import (
    MODEL,
    ONCALL_BAND_LOW,
    ONCALL_BANDS,
    ONCALL_CAUSE_ALERT_MISCONFIG,
    ONCALL_CAUSE_APP_BUG,
    ONCALL_CAUSE_CLASSES,
    ONCALL_CAUSE_INFRA_FAILURE,
    ONCALL_CAUSE_UNKNOWN,
    ONCALL_CONFIDENCE_FLOOR,
    ONCALL_DISPOSITION_FALSE_POSITIVE,
    ONCALL_DISPOSITION_NOISE,
    ONCALL_DISPOSITION_REAL,
    ONCALL_DISPOSITION_UNKNOWN,
    ONCALL_DISPOSITIONS,
    ONCALL_SEV1,
    ONCALL_SEV2,
    ONCALL_SEV3,
    ONCALL_SEV_NONE,
    ONCALL_SEVS,
    REASON_BELOW_CONFIDENCE,
    REASON_SELECTED,
    REASON_UNAVAILABLE,
    SOURCE_FALLBACK,
    SOURCE_TYPESAFE,
)

QUESTION_DISPOSITION = "disposition"
QUESTION_CAUSE_CLASS = "cause_class"
QUESTION_SEV = "sev"
QUESTION_CONFIDENCE_BAND = "confidence_band"
STATE_FIELDS = (
    "alert",
    "sentry",
    "cloudwatch",
    "ecs",
    "health",
    "deploys",
    "linear",
    "slack",
)
DISPOSITION_CRITERIA = {
    ONCALL_DISPOSITION_FALSE_POSITIVE: "Normal behavior; the rule or threshold is wrong.",
    ONCALL_DISPOSITION_REAL: "User impact or service degradation.",
    ONCALL_DISPOSITION_NOISE: "Fired on a non-symptom, not user impact.",
}
CAUSE_CRITERIA = {
    ONCALL_CAUSE_APP_BUG: "An application defect caused the alert.",
    ONCALL_CAUSE_INFRA_FAILURE: "Infrastructure failed under the alert.",
    ONCALL_CAUSE_ALERT_MISCONFIG: "The alert itself is misconfigured.",
    ONCALL_CAUSE_UNKNOWN: "The cause class is not yet known.",
}
SEV_CRITERIA = {
    ONCALL_SEV1: "Service down, users impacted, or data at risk.",
    ONCALL_SEV2: "Degraded service or partial impact.",
    ONCALL_SEV3: "Minor issue; a workaround exists.",
    ONCALL_SEV_NONE: "Not a real incident, so no severity.",
}
BAND_CRITERIA = (
    "Low: evidence is thin, conflicting, or missing.",
    "Medium: evidence supports the disposition with gaps.",
    "High: evidence clearly supports the disposition.",
)


@dataclass(frozen=True, slots=True)
class OncallResult:
    disposition: str
    cause_class: str
    sev: str
    confidence: float
    confidence_band: str
    source: str
    reason: str
    usage: dict[str, Any]

    def as_json(self) -> dict[str, Any]:
        return {
            "disposition": self.disposition,
            "cause_class": self.cause_class,
            "sev": self.sev,
            "confidence": self.confidence,
            "confidence_band": self.confidence_band,
            "source": self.source,
            "reason": self.reason,
            "usage": self.usage,
        }


def fallback(reason: str = REASON_UNAVAILABLE) -> OncallResult:
    return OncallResult(
        disposition=ONCALL_DISPOSITION_UNKNOWN,
        cause_class=ONCALL_CAUSE_UNKNOWN,
        sev=ONCALL_SEV_NONE,
        confidence=0.0,
        confidence_band=ONCALL_BAND_LOW,
        source=SOURCE_FALLBACK,
        reason=reason,
        usage={},
    )


def load_state(raw: str) -> dict[str, str]:
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise TypeError("classify-oncall stdin must be a JSON object")
    return {field: answers.text(payload.get(field)) for field in STATE_FIELDS}


def build_request(state: dict[str, str]) -> dict[str, Any]:
    return {
        "model": MODEL,
        "state": state,
        "questions": {
            QUESTION_DISPOSITION: {
                "type": "choice",
                "instructions": "What is the disposition of this alert given the evidence?",
                "criteria": dict(DISPOSITION_CRITERIA),
            },
            QUESTION_CAUSE_CLASS: {
                "type": "choice",
                "instructions": "What cause class fits the evidence? Name the class, not an action.",
                "criteria": dict(CAUSE_CRITERIA),
            },
            QUESTION_SEV: {
                "type": "choice",
                "instructions": (
                    "If this alert is real, what severity is it? Choose none when it is not real."
                ),
                "criteria": dict(SEV_CRITERIA),
            },
            QUESTION_CONFIDENCE_BAND: {
                "type": "score",
                "instructions": "How strong is the evidence for this disposition?",
                "criteria": list(BAND_CRITERIA),
            },
        },
    }


def band_for(score: float) -> str:
    index = min(max(round(score), 0), len(ONCALL_BANDS) - 1)
    return ONCALL_BANDS[index]


def sev_for(disposition: str, sev: str) -> str:
    if disposition != ONCALL_DISPOSITION_REAL:
        return ONCALL_SEV_NONE
    return sev


def decide(
    answers_by_id: dict[str, Any],
    _state: dict[str, str],
    usage: Any,
) -> OncallResult:
    disposition, confidence = answers.choice(answers_by_id, QUESTION_DISPOSITION)
    cause_class, _cause_confidence = answers.choice(answers_by_id, QUESTION_CAUSE_CLASS)
    sev, _sev_confidence = answers.choice(answers_by_id, QUESTION_SEV)
    if disposition not in ONCALL_DISPOSITIONS:
        raise ValueError("TypeSafe oncall disposition outside the closed set")
    if cause_class not in ONCALL_CAUSE_CLASSES:
        raise ValueError("TypeSafe oncall cause_class outside the closed set")
    if sev not in ONCALL_SEVS:
        raise ValueError("TypeSafe oncall sev outside the closed set")
    if confidence < ONCALL_CONFIDENCE_FLOOR:
        return fallback(REASON_BELOW_CONFIDENCE)
    return OncallResult(
        disposition=disposition,
        cause_class=cause_class,
        sev=sev_for(disposition, sev),
        confidence=confidence,
        confidence_band=band_for(answers.score(answers_by_id, QUESTION_CONFIDENCE_BAND)),
        source=SOURCE_TYPESAFE,
        reason=REASON_SELECTED,
        usage=usage if isinstance(usage, dict) else {},
    )
