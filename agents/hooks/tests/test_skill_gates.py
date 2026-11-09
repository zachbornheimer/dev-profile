"""Contract tests for the re-derivation gates in assume-session and debug-protocol (ZYS-1721, ZYS-1722).

The gates are instructions, so the test pins the clauses each acceptance
criterion names: if a clause is reworded away the suite fails.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

SKILLS = Path(__file__).resolve().parents[2] / "available-skills"


def skill_text(name: str) -> str:
    return re.sub(r"\s+", " ", (SKILLS / name / "SKILL.md").read_text())


@pytest.fixture(scope="module")
def assume() -> str:
    return skill_text("assume-session").lower()


@pytest.fixture(scope="module")
def debug() -> str:
    return skill_text("debug-protocol").lower()


@pytest.mark.parametrize(
    "clause",
    [
        "premise re-derivation comes before any inherited work",
        "restate the original user symptom",
        "in the user's own words",
        "falsifiable premises",
        "against current world state",
        "upstream prs, issues and releases included",
        "state the achievable minimum",
        "owner-config lever search",
        "before proposing patches, forks, or upstream prs",
        "approval does not waive this gate",
    ],
)
def test_assume_session_gate_clause(assume: str, clause: str) -> None:
    assert clause in assume


def test_assume_session_keeps_continuity(assume: str) -> None:
    assert "do not start a new project" in assume
    assert "finish the work that was in flight" in assume


def test_assume_session_description_advertises_lookup_by_id() -> None:
    text = (SKILLS / "assume-session" / "SKILL.md").read_text()
    description = text.split("---")[1].lower()
    for needle in (
        "analyze",
        "by id",
        "read-only lookup",
        "get_recent_turns",
        "never hand-grep",
    ):
        assert needle in description


def test_assume_session_lookup_mode_needs_no_then(assume: str) -> None:
    assert "lookup (default)" in assume
    assert "no takeover, no `--then`" in assume
    assert "if the request is ambiguous between the two, do lookup" in assume
    assert "(takeover mode only; lookup mode skips them)" in assume


def test_find_session_defers_content_analysis_to_assume_session() -> None:
    text = skill_text("find-session").lower()
    assert "assume-session lookup mode" in text


def test_assume_session_lookup_uses_get_transcript(assume: str) -> None:
    assert "`get_transcript` is the primary tool" in assume
    assert "get_annotated_transcript" not in assume


@pytest.mark.parametrize(
    "clause",
    [
        "before the first edit on a measured defect",
        "all four artifacts exist in writing",
        "**floor.**",
        "time budget",
        "unexplained remainder means the diagnosis is incomplete",
        "owner config + upstream",
        "upstream issues and releases",
        "why is this wrong at this layer?",
        "re-planned at the owner layer",
        "only the problem statement and the raw measurements",
        "never the diff and never your narrative",
        "what would make this fix unnecessary?",
    ],
)
def test_debug_protocol_closure_gate_clause(debug: str, clause: str) -> None:
    assert clause in debug


def test_debug_protocol_gate_precedes_gotchas(debug: str) -> None:
    assert debug.index("closure gate") < debug.index("gotchas")
