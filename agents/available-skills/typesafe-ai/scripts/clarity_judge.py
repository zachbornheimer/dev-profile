"""judge-clarity: is an agent's final message clear enough to stop?

The state is the message alone. Questions name the reader and the rule,
because a draft-only state has no other fields.

Block only on a clear failure of a rule that already separated a jargon-heavy
report from a pass. A middle score does not block. A message that is not a
report does not get the report rules. TypeSafe down is not a block; the hook
allows the stop.

Only the prose is judged: fenced blocks, inline code, and paths are stripped
first, since a command or a filename is shown, not explained, and scoring it
as jargon blocked six technical replies in one session. The block reason
names the threshold and the tokens that most likely tripped the rule, so one
rewrite can fix them instead of guessing.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

import answers
from constants import MODEL, REASON_UNAVAILABLE, SOURCE_FALLBACK, SOURCE_TYPESAFE

QUESTION_IS_EXPLANATION = "is_explanation"
QUESTION_PLAIN_OPENING = "plain_opening"
QUESTION_EVERYDAY_WORDS = "everyday_words"
QUESTION_COUNTS_IN_A_TABLE = "counts_in_a_table"

# The jargon report scored 0.02-0.05 on the rules below and 0.44-0.75 on the
# rules we do not block on. 0.20 is a clear fail. 0.80 is a clear report.
CLEAR_FAIL = 0.20
EXPLANATION_FLOOR = 0.80

FENCED_BLOCK_RE = re.compile(r"```.*?```", re.DOTALL)
INLINE_CODE_RE = re.compile(r"`[^`\n]+`")
PATH_RE = re.compile(r"(?:~|\$HOME)(?:/[\w.+@-]+)*|(?:/[\w.+@-]+){2,}")
# Names that read as jargon to a 15-year-old: snake_case, CamelCase, dotted
# filenames, and acronyms. A heuristic for the feedback line, not the verdict.
SPECIALIZED_TOKEN_RE = re.compile(
    r"\b[A-Za-z][A-Za-z0-9]*(?:_[A-Za-z0-9]+)+\b"
    r"|\b[A-Z][a-z0-9]+(?:[A-Z][a-z0-9]+)+\b"
    r"|\b[\w-]+\.(?:py|toml|json|md|sh|ts|js|yaml|yml|rs|go)\b"
    r"|\b[A-Z]{3,}\b"
)
MAX_OFFENDERS_NAMED = 8
# A message that is only code or paths has no prose to judge; it is shown, not explained.
REASON_NO_PROSE = "no prose to judge"

ACTION_ALLOW = "allow"
ACTION_BLOCK = "block"
BLOCK_NONE = "none"
BLOCK_UNCLEAR = "unclear"
REASON_JUDGED = "judged"

RULES = (
    QUESTION_PLAIN_OPENING,
    QUESTION_EVERYDAY_WORDS,
    QUESTION_COUNTS_IN_A_TABLE,
)

REWRITE = {
    QUESTION_PLAIN_OPENING: (
        "First three sentences: what is wrong, why it matters, and what to do next, "
        "in words a 15-year-old would use."
    ),
    QUESTION_EVERYDAY_WORDS: (
        "Every specialized name is either removed or defined in everyday words in the "
        "same sentence. Showing the name in use is not a definition."
    ),
    QUESTION_COUNTS_IN_A_TABLE: (
        "Where you compare three or more counts, put those counts in a markdown table."
    ),
}


def _noul(question: str, yes: str, no: str) -> dict[str, Any]:
    return {"type": "noul", "instructions": question, "criteria": {"true": yes, "false": no}}


def build_questions() -> dict[str, dict[str, Any]]:
    return {
        QUESTION_IS_EXPLANATION: _noul(
            "Is this a report or a recommendation a reader must understand in order to "
            "act, or to avoid missing a fact?",
            "It explains findings, recommends changes, or walks through a decision.",
            "It is a short status, a direct answer, a question, or code with a one-line note.",
        ),
        QUESTION_PLAIN_OPENING: _noul(
            "Do the first three sentences say what is wrong, why it matters, and what to "
            "do next, in words a 15-year-old would use?",
            "Those three sentences state all three, and they do not depend on an undefined tool name.",
            "Any of the three is missing, or a sentence depends on a tool name it does not explain.",
        ),
        QUESTION_EVERYDAY_WORDS: _noul(
            "Is every specialized name either absent, or explained in everyday words in the "
            "same sentence? A specialized name is a product, an internal tool, or a process "
            "name. An example of the name in use is not an explanation. Everyday words are "
            "words a 15-year-old would say out loud.",
            "No specialized name appears without that same-sentence explanation.",
            "At least one specialized name appears without that explanation.",
        ),
        QUESTION_COUNTS_IN_A_TABLE: _noul(
            "Where the text compares three or more counts, are those counts in a markdown "
            "table? If the text never compares three or more counts, answer yes.",
            "Each such comparison is a markdown table, or there is no such comparison.",
            "Three or more counts are compared in a paragraph or a loose list.",
        ),
    }


def prose_only(message: str) -> str:
    """The message with fenced blocks, inline code, and paths removed."""
    text = FENCED_BLOCK_RE.sub(" ", message)
    text = INLINE_CODE_RE.sub(" ", text)
    text = PATH_RE.sub(" ", text)
    return re.sub(r"[ \t]+", " ", text).strip()


def specialized_tokens(prose: str) -> list[str]:
    seen: dict[str, None] = {}
    for match in SPECIALIZED_TOKEN_RE.finditer(prose):
        seen.setdefault(match.group(0), None)
    return list(seen)[:MAX_OFFENDERS_NAMED]


def build_request(state: dict[str, str]) -> dict[str, Any]:
    return {"model": MODEL, "state": state["prose"], "questions": build_questions()}


def load_state(raw: str) -> dict[str, str]:
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise TypeError("judge-clarity stdin must be a JSON object")
    message = answers.text(payload.get("message")).strip()
    if not message:
        raise ValueError("judge-clarity needs a non-empty message")
    return {"message": message, "prose": prose_only(message)}


@dataclass(frozen=True, slots=True)
class ClarityVerdict:
    action: str
    block_kind: str
    reason: str
    source: str
    signals: dict[str, float]
    failed: tuple[str, ...]
    usage: dict[str, Any]

    def as_json(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "action": self.action,
            "block_kind": self.block_kind,
            "reason": self.reason,
            "signals": self.signals,
            "failed": list(self.failed),
            "usage": self.usage,
        }


def fallback(reason: str = REASON_UNAVAILABLE) -> ClarityVerdict:
    return ClarityVerdict(
        action=ACTION_ALLOW,
        block_kind=BLOCK_NONE,
        reason=reason,
        source=SOURCE_FALLBACK,
        signals={},
        failed=(),
        usage={},
    )


def _rewrite(failed: list[str], signals: dict[str, float], prose: str) -> str:
    lines = [
        ("Rewrite the last message before you stop. A 15-year-old who has not seen these "
        "tools must be able to act on it without rereading."),
    ]
    for rule in failed:
        lines.append(
            f"- {REWRITE[rule]} (TypeSafe: {rule} {signals[rule]:.2f}, blocks below {CLEAR_FAIL:.2f})."
        )
    offenders = specialized_tokens(prose)
    if offenders and QUESTION_EVERYDAY_WORDS in failed:
        lines.append("  Likely offenders: " + ", ".join(offenders) + ".")
    lines.append(
        "Code blocks, inline code, and paths were not scored; only the prose around them "
        "needs to change. Do not drop a claim that changes what the reader should do. "
        "Shorter is better only if those claims remain."
    )
    return "\n".join(lines)


def decide(
    answers_by_id: dict[str, Any],
    state: dict[str, str],
    usage: Any,
) -> ClarityVerdict:
    signals = {
        question: answers.noul(answers_by_id, question)
        for question in (QUESTION_IS_EXPLANATION, *RULES)
    }
    failed: list[str] = []
    if signals[QUESTION_IS_EXPLANATION] >= EXPLANATION_FLOOR:
        failed = [rule for rule in RULES if signals[rule] < CLEAR_FAIL]
    usage_dict = usage if isinstance(usage, dict) else {}
    if not failed:
        return ClarityVerdict(
            action=ACTION_ALLOW,
            block_kind=BLOCK_NONE,
            reason=REASON_JUDGED,
            source=SOURCE_TYPESAFE,
            signals=signals,
            failed=(),
            usage=usage_dict,
        )
    return ClarityVerdict(
        action=ACTION_BLOCK,
        block_kind=BLOCK_UNCLEAR,
        reason=_rewrite(failed, signals, state["prose"]),
        source=SOURCE_TYPESAFE,
        signals=signals,
        failed=tuple(failed),
        usage=usage_dict,
    )
