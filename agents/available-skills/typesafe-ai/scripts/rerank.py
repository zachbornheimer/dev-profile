"""pick-skill rerank: re-read the shortlist on SKILL.md excerpts and check fit."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import answers
from catalog import Skill, parse_frontmatter, skill_body
from constants import CHOICE_NONE, MODEL, PICK_EXCERPT_CHARS, PICK_FITS_THRESHOLD
from request_scope import prioritize_current

QUESTION_WHICH = "which"
FITS_PREFIX = "fits::"
WHICH_INSTRUCTIONS = (
    "Exactly one of these skills is the right one to load for the user's latest "
    "request. Which one? Read what each actually does, not just its name."
)


def describe(skill: Skill, text: str | None) -> tuple[str, str]:
    """(full description, criterion) — the criterion adds the SKILL.md excerpt."""
    if not text:
        return skill.description, skill.description or skill.name
    description = parse_frontmatter(text).get("description") or skill.description
    excerpt = skill_body(text)[:PICK_EXCERPT_CHARS]
    return description, f"{description} — {excerpt}" if excerpt else description


def build_request(
    state: dict[str, Any],
    shortlist: list[Skill],
    texts: Mapping[str, str | None],
) -> dict[str, Any]:
    described = {skill.name: describe(skill, texts.get(skill.name)) for skill in shortlist}
    criteria = {name: criterion for name, (_desc, criterion) in described.items()}
    if len(criteria) < 2:
        criteria[CHOICE_NONE] = "None of these skills fits the request."
    questions: dict[str, Any] = {
        QUESTION_WHICH: {"type": "choice", "instructions": WHICH_INSTRUCTIONS, "criteria": criteria}
    }
    for name, (description, _criterion) in described.items():
        questions[f"{FITS_PREFIX}{name}"] = {
            "type": "noul",
            "instructions": (
                f"Does the skill '{name}' do the specific thing the user's request asks "
                f"for? It is described as: {description}"
            ),
        }
    return prioritize_current({"model": MODEL, "state": state, "questions": questions})


def decide(
    reply: dict[str, Any],
    names: list[str],
) -> tuple[str, float, tuple[tuple[str, float], ...]]:
    """(winner or CHOICE_NONE, its confidence, every candidate's fit).

    The winner must clear the fit bar itself; another candidate's fit cannot carry it.
    """
    winner, confidence = answers.choice(reply, QUESTION_WHICH)
    fits = tuple((name, answers.noul(reply, f"{FITS_PREFIX}{name}")) for name in names)
    if winner not in names or dict(fits)[winner] < PICK_FITS_THRESHOLD:
        return CHOICE_NONE, confidence, fits
    return winner, confidence, fits
