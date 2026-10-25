"""Match amalgamated prompt answers to the scripts those answers start. No effects."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Route:
    """One row: a yes/no answer at or above `at_least` starts `argv`."""

    field: str
    at_least: float
    argv: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Routed:
    field: str
    argv: tuple[str, ...]


def routes_for(answers: Mapping[str, object], routes: Sequence[Route]) -> tuple[Routed, ...]:
    """Every route whose field is a number at or above its bar, in table order.

    A missing field, a bool, or a choice does not match. A yes/no answer is P(yes).
    """
    fired: list[Routed] = []
    for route in routes:
        value = answers.get(route.field)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        if value >= route.at_least:
            fired.append(Routed(route.field, _fill(route.argv, answers)))
    return tuple(fired)


def _fill(argv: Sequence[str], answers: Mapping[str, object]) -> tuple[str, ...]:
    filled: list[str] = []
    for arg in argv:
        if arg.startswith("{") and arg.endswith("}") and arg[1:-1] in answers:
            filled.append(_number(answers[arg[1:-1]]))
        else:
            filled.append(arg)
    return tuple(filled)


def _number(value: object) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return ""
    return f"{value:.2f}"
