"""Validated transcript, inference, and report boundaries."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Boundary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Message(Boundary):
    id: str
    session: str
    source: str
    line: int = Field(ge=1)
    date: str | None
    role: Literal["user", "assistant", "tool", "system"]
    text: str
    synthetic: bool = False


class Citation(Boundary):
    message_id: str
    quote: str = Field(min_length=1, max_length=600)


class Observation(Boundary):
    id: str
    category: Literal[
        "satisfaction",
        "quality",
        "communication",
        "prompt_act",
        "task_family",
        "goal",
        "decision",
        "lesson",
        "contradiction",
    ]
    claim: str = Field(min_length=1, max_length=1000)
    rating: Literal["unknown", "satisfied", "dissatisfied", "mixed", "verified", "failed"]
    scope: Literal["task-specific", "reusable"]
    evidence: list[Citation] = Field(min_length=1, max_length=4)
    uncertainty: str
    supersedes: list[str]


class Extraction(Boundary):
    observations: list[Observation] = Field(max_length=12)


class Noul(Boundary):
    type: Literal["noul"]
    noul: float = Field(ge=0, le=1, allow_inf_nan=False)


class DecisionResponse(BaseModel):
    model_config = ConfigDict(extra="allow")
    answers: dict[str, Noul]


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="allow")
    content: str


class ChatChoice(BaseModel):
    model_config = ConfigDict(extra="allow")
    message: ChatMessage
    finish_reason: str | None = None


class ChatResponse(BaseModel):
    model_config = ConfigDict(extra="allow")
    choices: list[ChatChoice] = Field(min_length=1)
