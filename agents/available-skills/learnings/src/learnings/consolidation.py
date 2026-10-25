"""Generation-only schema and bounded whole-response regeneration."""

import json
from dataclasses import dataclass
from typing import Literal

from pydantic import Field, ValidationError

from learnings.edges import Calls
from learnings.models import Boundary, ChatResponse, Extraction, Message

GENERATOR = "gpt-oss:latest"
MAX_OBSERVATIONS = 3
MAX_QUOTE = 160
DEFAULT_ATTEMPTS = 3
DEFAULT_TOKEN_CAP = 3200
DEFAULT_TOKEN_STEP = 700
REPAIR = """REGENERATE complete concise JSON from ORIGINAL data, not previous output.
Previous response failed: {reason}. Use at most 3 observations, exact quotes <=160 characters,
short claims and uncertainty. Rating unknown except category-valid satisfaction/quality ratings.
Do not repair JSON fragments, rewrite evidence, or invent approval. Return fewer observations
when necessary; finish the entire object within the budget. No prose or markdown."""


class GenerationCitation(Boundary):
    message_id: str
    quote: str = Field(min_length=1, max_length=MAX_QUOTE)


class GenerationObservation(Boundary):
    id: str
    claim: str = Field(min_length=1, max_length=1000)
    scope: Literal["task-specific", "reusable"]
    evidence: list[GenerationCitation] = Field(min_length=1, max_length=4)
    uncertainty: str
    supersedes: list[str]


class Satisfaction(GenerationObservation):
    category: Literal["satisfaction"]
    rating: Literal["unknown", "satisfied", "dissatisfied", "mixed"]


class Quality(GenerationObservation):
    category: Literal["quality"]
    rating: Literal["unknown", "verified", "failed"]


class Unrated(GenerationObservation):
    category: Literal[
        "communication", "prompt_act", "task_family", "goal", "decision", "lesson", "contradiction"
    ]
    rating: Literal["unknown"]


class Generation(Boundary):
    observations: list[Satisfaction | Quality | Unrated] = Field(max_length=MAX_OBSERVATIONS)


@dataclass(frozen=True, slots=True)
class Recovery:
    attempts: int = DEFAULT_ATTEMPTS
    token_cap: int = DEFAULT_TOKEN_CAP
    token_step: int = DEFAULT_TOKEN_STEP

    def validate(self, initial_tokens: int) -> None:
        if not 1 <= self.attempts <= DEFAULT_ATTEMPTS:
            raise ValueError("consolidation attempts must be between 1 and 3")
        if initial_tokens <= 0 or self.token_cap < initial_tokens or self.token_step < 0:
            raise ValueError("consolidation budget: positive, within cap; growth nonnegative")


def request(
    messages: list[Message], instructions: str, tokens: int, legacy: bool
) -> dict[str, object]:
    schema = Extraction.model_json_schema() if legacy else Generation.model_json_schema()
    return {
        "model": GENERATOR,
        "stream": False,
        "temperature": 0,
        "max_tokens": tokens,
        "reasoning_effort": "low",
        "messages": [
            {"role": "system", "content": instructions + "\nSCHEMA:\n" + json.dumps(schema)},
            {"role": "user", "content": json.dumps([m.model_dump() for m in messages])},
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "session_observations", "strict": True, "schema": schema},
        },
    }


def parse(raw: object, legacy: bool) -> Extraction:
    choice = ChatResponse.model_validate(raw).choices[0]
    if legacy:
        return Extraction.model_validate_json(choice.message.content)
    if choice.finish_reason == "length":
        raise ValueError("finish_reason_length")
    generation = Generation.model_validate_json(choice.message.content)
    return Extraction.model_validate(generation.model_dump())


@dataclass(frozen=True, slots=True)
class GenerationSettings:
    instructions: str
    tokens: int
    recovery: Recovery
    legacy: bool = False


async def generate(
    messages: list[Message], calls: Calls, settings: GenerationSettings
) -> Extraction:
    instructions, tokens = settings.instructions, settings.tokens
    recovery, legacy = settings.recovery, settings.legacy
    if not legacy:
        recovery.validate(tokens)
    reason = ""
    attempts = 1 if legacy else recovery.attempts
    for attempt in range(attempts):
        budget = (
            tokens if legacy else min(tokens + attempt * recovery.token_step, recovery.token_cap)
        )
        prompt = instructions if not attempt else instructions + "\n" + REPAIR.format(reason=reason)
        raw = await calls.request(
            "consolidate", "/v1/chat/completions", request(messages, prompt, budget, legacy)
        )
        try:
            return parse(raw, legacy)
        except (ValidationError, ValueError) as exc:
            if legacy:
                raise
            reason = (
                "schema_or_json_invalid"
                if isinstance(exc, ValidationError)
                else "finish_reason_length"
            )
            calls.records[-1]["validation"] = reason
            calls.save(
                f"{calls.count:03d}-consolidate-validation",
                {"attempt": attempt + 1, "reason": reason, "max_tokens": budget},
            )
    raise ValueError(f"consolidation exhausted {attempts} attempts: {reason}") from None
