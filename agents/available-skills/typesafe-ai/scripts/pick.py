"""pick-skill request and policy."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any

from answers import choice_distribution
from answers import noul as read_noul
from catalog import Skill
from constants import (
    CHOICE_NONE,
    IN_FLIGHT_NONE,
    LOCAL_PICK_MIN_SCORE,
    LOCAL_PICK_MIN_TOKEN_LENGTH,
    LOCAL_PICK_NAME_BONUS,
    LOCAL_PICK_STOPWORDS,
    MODEL,
    NEEDS_SKILL_THRESHOLD,
    PICK_CHOICE_MAX_OPTIONS,
    PICK_CHOICE_MAX_OPTIONS_BY_BASE_URL,
    PICK_SHORTLIST,
    QUESTION_SECOND_PRODUCT,
    QUESTION_SESSION_RELATION,
    REASON_BELOW_THRESHOLD,
    REASON_NO_FIT,
    REASON_NONE,
    REASON_SELECTED,
    REASON_UNAVAILABLE,
    SECOND_PRODUCT_THRESHOLD,
    SESSION_RELATION_LEVELS,
    SESSION_RELATION_TOP_LEVEL,
    SOURCE_FALLBACK,
    SOURCE_TYPESAFE,
)
from request_scope import prioritize_current

_TOKEN_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
_PART_RE = re.compile(r"[a-z0-9]+")

SKILL_PREFIX = "skill::"
GATE_PREFIX = "gate::"
# Minimum probability that the prompt is a distinct task before recommending a
# fresh session. Keep this beside the decision that consumes it so the routing
# policy is easy to tune.
SESSION_SPLIT_PROBABILITY_THRESHOLD = 0.45
SKILL_INSTRUCTIONS = (
    "Which of these skills, if any, is the right one to load to help with the "
    "user's latest request?"
)
# Request nouls from the cookbook: they ask whether an action is wanted, which a
# question about subject matter cannot separate. Their mean is the needs-skill gate.
GATE_QUESTIONS = {
    "acts_on_user_system": (
        "Is the assistant being asked to act on the user's files, accounts, devices, "
        "or online services, rather than only to explain or advise?"
    ),
    "would_follow_documented_procedure": (
        "Would a careful expert answering this consult a specific documented procedure "
        "or set of commands, rather than answering from general understanding?"
    ),
    "prose_suffices": (
        "Could a knowledgeable generalist fully satisfy this request in prose, with "
        "no tools, no documentation, and no access to the user's files or accounts?"
    ),
}
INVERTED_GATES = frozenset({"prose_suffices"})

# TypeSafe picker questions live here. Add or change a question in this section,
# then include it from build_questions(); request assembly stays below.


def roster_chunks(skills: list[Skill], max_options: int) -> list[list[Skill]]:
    """Round-robin chunks small enough for one Choice each, with room for "none"."""
    count = max(1, math.ceil(len(skills) / (max_options - 1)))
    return [skills[index::count] for index in range(count)]


def build_skill_questions(
    skills: list[Skill], max_options: int = PICK_CHOICE_MAX_OPTIONS
) -> dict[str, dict[str, Any]]:
    questions: dict[str, dict[str, Any]] = {}
    for index, chunk in enumerate(roster_chunks(skills, max_options)):
        criteria = {skill.name: skill.description or skill.name for skill in chunk}
        criteria[CHOICE_NONE] = "None of the skills in this list fit the request."
        questions[f"{SKILL_PREFIX}{index}"] = {
            "type": "choice",
            "instructions": SKILL_INSTRUCTIONS,
            "criteria": criteria,
        }
    return questions


def build_gate_questions() -> dict[str, dict[str, Any]]:
    return {
        f"{GATE_PREFIX}{key}": {"type": "noul", "instructions": text}
        for key, text in GATE_QUESTIONS.items()
    }


def build_session_relation_question() -> dict[str, Any]:
    return {
        "type": "score",
        "instructions": (
            "How does `prompt` relate to the work already in flight "
            "(`in_flight`)? Round outcomes are the levels themselves."
        ),
        "criteria": [
            f"{level['what']} Examples: {'; '.join(level['examples'])}."
            for level in SESSION_RELATION_LEVELS
        ],
    }


def for_base(request: dict[str, Any], skills: list[Skill], base: str) -> dict[str, Any]:
    """The wide request with its roster chunked to fit ``base``'s Choice limit."""
    limit = PICK_CHOICE_MAX_OPTIONS_BY_BASE_URL.get(base, PICK_CHOICE_MAX_OPTIONS)
    kept = {
        k: v for k, v in request["questions"].items() if not k.startswith(SKILL_PREFIX)
    }
    return prioritize_current(
        {**request, "questions": {**build_skill_questions(skills, limit), **kept}}
    )


def build_questions(skills: list[Skill]) -> dict[str, dict[str, Any]]:
    """Return the complete, ordered TypeSafe question set for the wide rank."""
    return {
        **build_skill_questions(skills),
        **build_gate_questions(),
        QUESTION_SESSION_RELATION: build_session_relation_question(),
    }


@dataclass(frozen=True, slots=True)
class PickResult:
    choice: str
    confidence: float
    needs_skill: float
    source: str
    reason: str
    usage: dict[str, Any]
    load: tuple[str, ...] = ()
    paths: tuple[str, ...] = ()
    second_product: float = 0.0
    session_relation: float = 0.0
    split: bool = False
    shortlist: tuple[str, ...] = ()
    fits: tuple[tuple[str, float], ...] = ()

    def as_json(self) -> dict[str, Any]:
        return {
            "choice": self.choice,
            "confidence": self.confidence,
            "needs_skill": self.needs_skill,
            "source": self.source,
            "reason": self.reason,
            "usage": self.usage,
            "load": list(self.load),
            "paths": list(self.paths),
            "second_product": self.second_product,
            "session_relation": self.session_relation,
            "split": self.split,
            "shortlist": list(self.shortlist),
            "fits": dict(self.fits),
        }


def fallback(reason: str = REASON_UNAVAILABLE) -> PickResult:
    return PickResult(
        choice=CHOICE_NONE,
        confidence=0.0,
        needs_skill=0.0,
        source=SOURCE_FALLBACK,
        reason=reason,
        usage={},
        second_product=0.0,
        session_relation=0.0,
        split=False,
    )


def local_pick(
    prompt: str,
    skills: list[Skill],
    reason: str = REASON_UNAVAILABLE,
) -> PickResult:
    scored = [(_skill_score(prompt, skill), skill.name) for skill in skills]
    if not scored:
        return fallback(reason)
    best = max(score for score, _name in scored)
    winners = [name for score, name in scored if score == best]
    if best < LOCAL_PICK_MIN_SCORE or len(winners) != 1:
        return fallback(reason)
    return PickResult(
        choice=winners[0],
        confidence=0.0,
        needs_skill=0.0,
        source=SOURCE_FALLBACK,
        reason=reason,
        usage={},
        load=_files_to_load(skills, winners[0]),
        paths=_paths_to_load(skills, winners[0]),
        second_product=0.0,
        session_relation=0.0,
        split=False,
    )


def _files_to_load(skills: list[Skill], choice: str) -> tuple[str, ...]:
    for skill in skills:
        if skill.name == choice:
            return skill.load or (choice,)
    return (choice,)


def _paths_to_load(skills: list[Skill], choice: str) -> tuple[str, ...]:
    by_name = {skill.name: skill for skill in skills}
    chosen = by_name.get(choice)
    if chosen is None:
        return ()
    if chosen.load_paths:
        return chosen.load_paths
    paths: list[str] = []
    for name in _files_to_load(skills, choice):
        path = by_name.get(name)
        if path is not None and path.path:
            paths.append(path.path)
    return tuple(paths)


def _tokens(text: str) -> set[str]:
    tokens: set[str] = set()
    for raw in _PART_RE.findall(text.lower()):
        if len(raw) < LOCAL_PICK_MIN_TOKEN_LENGTH:
            continue
        if raw in LOCAL_PICK_STOPWORDS:
            continue
        tokens.add(raw)
    return tokens


def _skill_tokens(skill: Skill) -> set[str]:
    name = skill.name.lower()
    tokens = _tokens(name.replace("-", " "))
    tokens |= _tokens(skill.description)
    tokens.add(name)
    return tokens


def _skill_score(prompt: str, skill: Skill) -> int:
    score = len(_tokens(prompt) & _skill_tokens(skill))
    if skill.name.lower() in set(_TOKEN_RE.findall(prompt.lower())):
        score += LOCAL_PICK_NAME_BONUS
    return score


def _state_in_flight(in_flight: str) -> str:
    text = in_flight.strip()
    return text or IN_FLIGHT_NONE


def _has_in_flight(in_flight: str) -> bool:
    text = in_flight.strip()
    return bool(text) and text != IN_FLIGHT_NONE


def build_request(
    prompt: str,
    skills: list[Skill],
    in_flight: str = "",
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    state: dict[str, Any] = {
        "prompt": prompt,
        "in_flight": _state_in_flight(in_flight),
    }
    if context:
        state["context"] = context
    return prioritize_current(
        {
            "model": MODEL,
            "state": state,
            "questions": build_questions(skills),
        }
    )


def _noul_or_zero(answers: dict[str, Any], question: str) -> float:
    answer = answers.get(question)
    if not isinstance(answer, dict) or answer.get("type") != "noul":
        return 0.0
    if "noul" not in answer:
        return 0.0
    raw = answer["noul"]
    if isinstance(raw, bool) or raw is None:
        return 0.0
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 0.0


def _probability_at(probabilities: object, level: int) -> float:
    if not isinstance(probabilities, dict):
        return 0.0
    for key in (str(level), level):
        if key not in probabilities:
            continue
        raw = probabilities[key]
        if isinstance(raw, bool) or raw is None:
            return 0.0
        try:
            return float(raw)
        except (TypeError, ValueError):
            return 0.0
    return 0.0


def _nearest_level(score: float) -> int:
    return min(max(int(score + 0.5), 0), SESSION_RELATION_TOP_LEVEL)


def _session_fields(
    answers: dict[str, Any],
    in_flight: str,
    has_context: bool = False,
) -> tuple[float, float, bool]:
    """Return (session_relation, second_product, split)."""
    answer = answers.get(QUESTION_SESSION_RELATION)
    if isinstance(answer, dict) and answer.get("type") == "score" and "score" in answer:
        raw_score = answer["score"]
        if isinstance(raw_score, bool) or raw_score is None:
            session_relation = 0.0
        else:
            try:
                session_relation = float(raw_score)
            except (TypeError, ValueError):
                session_relation = 0.0
        second_product = _probability_at(
            answer.get("probabilities"),
            SESSION_RELATION_TOP_LEVEL,
        )
        nearest = _nearest_level(session_relation)
        split = (
            (has_context or _has_in_flight(in_flight))
            and nearest == SESSION_RELATION_TOP_LEVEL
            and second_product >= SESSION_SPLIT_PROBABILITY_THRESHOLD
        )
        return session_relation, second_product, split

    second_product = _noul_or_zero(answers, QUESTION_SECOND_PRODUCT)
    split = (
        has_context or _has_in_flight(in_flight)
    ) and second_product >= SECOND_PRODUCT_THRESHOLD
    return 0.0, second_product, split


@dataclass(frozen=True, slots=True)
class Wide:
    """The wide rank's reading, before any rerank."""

    ranked: tuple[tuple[str, float], ...]
    needs_skill: float
    session_relation: float
    second_product: float
    split: bool
    usage: dict[str, Any]

    def shortlist(self) -> list[str]:
        return [name for name, _probability in self.ranked[:PICK_SHORTLIST]]


def read_wide(
    answers: dict[str, Any],
    skills: list[Skill],
    usage: Any,
    in_flight: str = "",
    has_context: bool = False,
) -> Wide:
    roster = {skill.name for skill in skills}
    probabilities: dict[str, float] = {}
    chunks = sorted(key for key in answers if key.startswith(SKILL_PREFIX))
    if not chunks:
        raise ValueError(f"TypeSafe answer {SKILL_PREFIX}* missing")
    for key in chunks:
        for name, value in choice_distribution(answers, key).items():
            if name in roster:
                probabilities[name] = value
    gates = [
        1.0 - read_noul(answers, f"{GATE_PREFIX}{key}")
        if key in INVERTED_GATES
        else read_noul(answers, f"{GATE_PREFIX}{key}")
        for key in GATE_QUESTIONS
    ]
    session_relation, second_product, split = _session_fields(
        answers, in_flight, has_context
    )
    return Wide(
        ranked=tuple(sorted(probabilities.items(), key=lambda item: -item[1])),
        needs_skill=sum(gates) / len(gates),
        session_relation=session_relation,
        second_product=second_product,
        split=split,
        usage=usage if isinstance(usage, dict) else {},
    )


def result(
    wide: Wide,
    skills: list[Skill],
    reason: str,
    *,
    choice: str = CHOICE_NONE,
    confidence: float = 0.0,
    fits: tuple[tuple[str, float], ...] = (),
) -> PickResult:
    chosen = choice != CHOICE_NONE
    return PickResult(
        choice=choice,
        confidence=confidence,
        needs_skill=wide.needs_skill,
        source=SOURCE_TYPESAFE,
        reason=reason,
        usage=wide.usage,
        load=_files_to_load(skills, choice) if chosen else (),
        paths=_paths_to_load(skills, choice) if chosen else (),
        second_product=wide.second_product,
        session_relation=wide.session_relation,
        split=wide.split,
        shortlist=tuple(wide.shortlist()),
        fits=fits,
    )


def gate(wide: Wide, skills: list[Skill]) -> PickResult | None:
    """A no-skill result when the wide rank already settles it, else None (rerank)."""
    if wide.needs_skill < NEEDS_SKILL_THRESHOLD:
        return result(wide, skills, REASON_BELOW_THRESHOLD)
    if not wide.ranked:
        return result(wide, skills, REASON_NONE)
    return None


def settle(
    wide: Wide,
    skills: list[Skill],
    choice: str,
    confidence: float,
    fits: tuple[tuple[str, float], ...],
) -> PickResult:
    if choice == CHOICE_NONE:
        return result(wide, skills, REASON_NO_FIT, confidence=confidence, fits=fits)
    return result(
        wide, skills, REASON_SELECTED, choice=choice, confidence=confidence, fits=fits
    )
