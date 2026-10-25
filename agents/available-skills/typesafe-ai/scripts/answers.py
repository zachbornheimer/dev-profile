"""TypeSafe answer field readers."""

from __future__ import annotations

from typing import Any


def choice(answers: dict[str, Any], question: str) -> tuple[str, float]:
    answer = answers.get(question)
    if not isinstance(answer, dict) or answer.get("type") != "choice":
        raise ValueError(f"TypeSafe answer {question} missing choice fields")
    if "choice" not in answer:
        raise ValueError(f"TypeSafe answer {question} missing choice")
    return str(answer["choice"]), float(answer.get("confidence") or 0.0)


def choice_distribution(answers: dict[str, Any], question: str) -> dict[str, float]:
    """The full option->probability distribution behind a Choice answer — needed by
    beam search and other algorithms that must rank or combine more than the single
    winning `choice`. Raises the same way `choice()` does when the answer is missing
    or malformed, so a caller can never silently beam-search over an empty map."""
    answer = answers.get(question)
    if not isinstance(answer, dict) or answer.get("type") != "choice":
        raise ValueError(f"TypeSafe answer {question} missing choice fields")
    probabilities = answer.get("probabilities")
    if not isinstance(probabilities, dict) or not probabilities:
        raise ValueError(f"TypeSafe answer {question} missing probabilities")
    return {str(option): float(value) for option, value in probabilities.items()}


def noul(answers: dict[str, Any], question: str) -> float:
    answer = answers.get(question)
    if not isinstance(answer, dict) or answer.get("type") != "noul":
        raise ValueError(f"TypeSafe answer {question} missing noul")
    if "noul" not in answer:
        raise ValueError(f"TypeSafe answer {question} missing noul")
    return float(answer["noul"])


def score(answers: dict[str, Any], question: str) -> float:
    answer = answers.get(question)
    if not isinstance(answer, dict) or answer.get("type") != "score":
        raise ValueError(f"TypeSafe answer {question} missing score fields")
    if "score" not in answer:
        raise ValueError(f"TypeSafe answer {question} missing score")
    return float(answer["score"])


def text(value: object) -> str:
    return "" if value is None else str(value)


def texts(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [text(item) for item in value if item is not None]
