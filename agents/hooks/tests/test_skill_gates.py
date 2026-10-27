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
