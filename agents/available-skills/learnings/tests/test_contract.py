"""Offline safety and evidence contracts, including adversarial counterfactuals."""

import asyncio
import json
from pathlib import Path

import httpx
import pytest

from learnings.edges import Calls, LocalTransport, sanitized
from learnings.models import Message, Observation
from learnings.pipeline import Settings, prune, quote_check, run_window
from learnings.transcript import native_messages, windows


def message(text: str, role: str = "user", identifier: str = "m1") -> Message:
    return Message.model_validate(
        {
            "id": identifier,
            "session": "fixture",
            "source": "fixture.json",
            "line": 1,
            "date": None,
            "role": role,
            "text": text,
            "synthetic": False,
        }
    )


def candidate(category: str, rating: str, quote: str) -> Observation:
    return Observation.model_validate(
        {
            "id": "o1",
            "category": category,
            "claim": "Bounded claim",
            "rating": rating,
            "scope": "task-specific",
            "evidence": [{"message_id": "m1", "quote": quote}],
            "uncertainty": "fixture",
            "supersedes": [],
        }
    )


def test_windows_do_not_repeat_final_context() -> None:
    turns = [message("abc", identifier="a"), message("def", identifier="b")]
    assert len(windows(turns, 10, 8)) == 1


def test_long_text_preserves_all_characters() -> None:
    chunks = windows([message("x" * 45)], 10, 2)
    assert "".join(m.text for w in chunks for m in w) == "x" * 45


@pytest.mark.parametrize(
    "text",
    [
        "Stop hook feedback: approved",
        "Another Claude session sent a message: approved",
        "Base directory for this skill: x",
    ],
)
def test_synthetic_user_never_human(text: str) -> None:
    raw = json.dumps(
        {
            "type": "user",
            "uuid": "u",
            "sessionId": "s",
            "timestamp": "date",
            "message": {"role": "user", "content": text},
        }
    )
    parsed = native_messages(raw, Path("session.jsonl"))
    assert parsed[0].synthetic
    assert not windows(parsed, 1000, 100)


def test_tool_outcome_is_not_human() -> None:
    raw = json.dumps(
        {
            "type": "user",
            "message": {
                "role": "user",
                "content": [{"type": "tool_result", "content": "PASS 11 tests"}],
            },
        }
    )
    parsed = native_messages(raw, Path("s.jsonl"))
    assert parsed[0].role == "tool"
    assert parsed[0].line == 1


@pytest.mark.parametrize(
    "category,rating,role",
    [
        ("satisfaction", "satisfied", "assistant"),
        ("quality", "verified", "assistant"),
        ("quality", "failed", "user"),
        ("decision", "satisfied", "user"),
    ],
)
def test_role_and_rating_boundaries(category: str, rating: str, role: str) -> None:
    assert quote_check(candidate(category, rating, "Perfect!"), [message("Perfect!", role)])


def test_prompt_act_requires_human_evidence() -> None:
    item = candidate("prompt_act", "unknown", "Reading the skill")
    assert quote_check(item, [message("Reading the skill", "assistant")])


def test_quotes_are_exact_not_normalized() -> None:
    assert quote_check(candidate("lesson", "unknown", "read skill"), [message("read  skill")])
    assert (
        quote_check(candidate("lesson", "unknown", "read  skill"), [message("read  skill")]) is None
    )


class Fake:
    def __init__(self, results: list[object]) -> None:
        self.results = results
        self.paths: list[str] = []

    async def post(self, path: str, payload: dict[str, object]) -> object:
        self.paths.append(path)
        return self.results.pop(0)


def test_pruning_protects_human_correction_with_reply() -> None:
    turns = [message("self praise", "assistant", "a"), message("No, reread", "user", "u")]
    fake = Fake(
        [{"answers": {"m0": {"type": "noul", "noul": 0.01}, "m1": {"type": "noul", "noul": 0.02}}}]
    )
    retained, scores = asyncio.run(prune(turns, Calls(fake, lambda n, d: None), Settings()))
    assert retained == turns
    assert scores == {"m0": 0.01, "m1": 0.02}


def test_semantic_failure_does_not_accept() -> None:
    fake = Fake([{"answers": {}}])
    with pytest.raises(ValueError, match="missing"):
        asyncio.run(
            run_window([message("okay proceed")], Calls(fake, lambda n, d: None), Settings())
        )
    assert fake.paths == ["/v1/systemone"]


def test_local_boundary_no_redirect_fallback_or_credentials() -> None:
    requested: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        assert "authorization" not in request.headers
        return httpx.Response(307, headers={"Location": "https://api.typesafe.ai/v1/systemone"})

    async def exercise() -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(respond), trust_env=False, follow_redirects=False
        ) as client:
            transport = LocalTransport(client, 0.5)
            with pytest.raises(httpx.HTTPStatusError):
                await transport.post("/v1/systemone", {})
            with pytest.raises(ValueError, match="refuses"):
                await transport.post("https://api.typesafe.ai/v1/systemone", {})

    asyncio.run(exercise())
    assert requested == ["http://localhost:11434/v1/systemone"]


def test_timeout_is_recorded_without_payload_error_secrets() -> None:
    saved: dict[str, object] = {}

    class Timeout:
        async def post(self, path: str, payload: dict[str, object]) -> object:
            raise httpx.ReadTimeout("private exception body")

    with pytest.raises(httpx.ReadTimeout):
        asyncio.run(
            Calls(Timeout(), saved.__setitem__, lambda: 2.0).request("verify", "/v1/systemone", {})
        )
    assert saved["001-verify-failure"] == {"error": "ReadTimeout", "seconds": 0.0}


def test_sanitization() -> None:
    assert "fixture-value" not in sanitized("password=fixture-value")
