"""Completed report schema and explicit unknown dimensions."""

from typing import Literal

from pydantic import Field

from learnings.models import Boundary, Observation

DIMENSIONS = (
    "satisfaction",
    "quality",
    "communication",
    "prompt_act",
    "task_family",
    "goal",
    "decision",
    "lesson",
    "contradiction",
)


class Finding(Boundary):
    candidate: Observation
    probabilities: dict[str, float]
    status: Literal["review-candidate", "unknown-or-rejected"]
    reason: str | None


class WindowReport(Boundary):
    input_chars: int = Field(ge=1)
    retained_chars: int = Field(ge=0)
    input_messages: int = Field(ge=1)
    retained_messages: int = Field(ge=0)
    pruning_probabilities: dict[str, float]
    observations: list[Finding]
    window: int = Field(ge=0)
    source_messages: list[dict[str, object]] = Field(min_length=1)


class CompletedReport(Boundary):
    status: Literal["completed"]
    accepted_rules: list[object] = Field(max_length=0)
    sampled: Literal[True]
    probability_note: str
    thresholds: str
    mode: Literal["baseline", "prune-consolidate-verify"]
    source: str
    session_ids: list[str] = Field(min_length=1)
    line_range: tuple[int, int | None]
    window_count: int = Field(ge=1)
    excluded_synthetic: int = Field(ge=0)
    windows: list[WindowReport] = Field(min_length=1)
    cross_window_note: str
    dimension_coverage: dict[str, str] | None = None
    recovery: dict[str, int] | None = None
    calls: list[dict[str, object]] | None = None


def coverage(windows: list[WindowReport]) -> dict[str, str]:
    retained = {
        finding.candidate.category
        for window in windows
        for finding in window.observations
        if finding.status == "review-candidate"
    }
    return {
        dimension: "review-candidate; not validated coverage"
        if dimension in retained
        else "unknown"
        for dimension in DIMENSIONS
    }
