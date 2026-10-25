"""Bounded regeneration never repairs evidence or escapes local transport."""

import asyncio
import json
from pathlib import Path

import httpx
import pytest
from test_contract import candidate, message

from learnings.consolidation import Recovery
from learnings.edges import Calls, Files
from learnings.pipeline import Settings, consolidate, run_window


class Sequence:
    def __init__(self, responses: list[object]) -> None:
        self.responses = responses
        self.requests: list[dict[str, object]] = []

    async def post(self, path: str, payload: dict[str, object]) -> object:
        assert path in {"/v1/chat/completions", "/v1/systemone"}
        self.requests.append(payload)
        result = self.responses.pop(0)
        if isinstance(result, httpx.HTTPError):
            raise result
        return result


def chat(content: str, finish: str = "stop") -> dict[str, object]:
    return {"choices": [{"message": {"content": content}, "finish_reason": finish}]}


def valid() -> str:
    return json.dumps({"observations": [candidate("lesson", "unknown", "read skill").model_dump()]})


def invalid(kind: str) -> object:
    if kind == "truncated":
        return chat('{"observations":[')
    if kind == "length":
        return chat(valid(), "length")
    item = candidate("lesson", "unknown", "read skill").model_dump()
    if kind == "quote":
        item["evidence"] = [{"message_id": "m1", "quote": "x" * 161}]
    elif kind == "rating":
        item["rating"] = "verified"
    elif kind == "count":
        return chat(json.dumps({"observations": [item] * 4}))
    return chat(json.dumps({"observations": [item]}))


@pytest.mark.parametrize("kind", ["truncated", "length", "quote", "rating", "count"])
def test_invalid_generation_regenerates_without_coercion(kind: str) -> None:
    transport = Sequence([invalid(kind), chat(valid())])
    saved: dict[str, object] = {}
    result = asyncio.run(
        consolidate([message("read skill")], Calls(transport, saved.__setitem__), Settings())
    )
    assert result.observations[0].rating == "unknown"
    assert len(transport.requests) == 2
    assert "001-consolidate-response" in saved
    assert "002-consolidate-response" in saved
    first, second = (request["max_tokens"] for request in transport.requests)
    assert isinstance(first, int) and isinstance(second, int)
    assert first < second
    assert "REGENERATE" in json.dumps(transport.requests[1])


def test_exhaustion_is_bounded_and_errors_omit_content() -> None:
    transport = Sequence([chat("PRIVATE transcript fragment")] * 3)
    with pytest.raises(ValueError, match="exhausted") as error:
        asyncio.run(
            consolidate([message("read skill")], Calls(transport, lambda n, d: None), Settings())
        )
    assert "PRIVATE" not in str(error.value)
    assert len(transport.requests) == 3


def test_timeout_is_not_retried_or_hosted() -> None:
    transport = Sequence([httpx.ReadTimeout("PRIVATE")])
    saved: dict[str, object] = {}
    with pytest.raises(httpx.ReadTimeout):
        asyncio.run(
            consolidate([message("read skill")], Calls(transport, saved.__setitem__), Settings())
        )
    assert len(transport.requests) == 1
    failure = saved["001-consolidate-failure"]
    assert isinstance(failure, dict)
    assert failure["error"] == "ReadTimeout"


def test_repaired_generation_still_passes_semantic_gates() -> None:
    rejected = {
        "answers": {
            key: {"type": "noul", "noul": 0.01} for key in ("supported", "useful", "explicit")
        }
    }
    transport = Sequence([invalid("truncated"), chat(valid()), rejected])
    result = asyncio.run(
        run_window(
            [message("read skill")], Calls(transport, lambda n, d: None), Settings(baseline=True)
        )
    )
    findings = result["observations"]
    assert isinstance(findings, list)
    assert findings[0]["status"] == "unknown-or-rejected"


@pytest.mark.parametrize("run", ["dev-profile-1", "dev-profile-revised-7", "dev-profile-revised-8"])
def test_captured_historical_failure_recovers(run: str) -> None:
    root = Path.home() / ".hermes/profiles/zach/cache/scratch/learnings" / run
    raw = json.loads(Files().read(root / "002-consolidate-response.json"))["raw"]
    transport = Sequence([raw, chat(valid())])
    result = asyncio.run(
        consolidate([message("read skill")], Calls(transport, lambda n, d: None), Settings())
    )
    assert len(transport.requests) == 2
    assert result.observations[0].evidence[0].quote == "read skill"


@pytest.mark.parametrize(
    "category,rating", [("satisfaction", "verified"), ("quality", "satisfied")]
)
def test_category_invalid_ratings_regenerate(category: str, rating: str) -> None:
    item = candidate(category, rating, "read skill").model_dump()
    transport = Sequence([chat(json.dumps({"observations": [item]})), chat(valid())])
    asyncio.run(
        consolidate([message("read skill")], Calls(transport, lambda n, d: None), Settings())
    )
    assert len(transport.requests) == 2


def test_configured_attempts_and_token_cap() -> None:
    transport = Sequence([invalid("truncated")] * 2)
    settings = Settings(
        max_tokens=1200, recovery=Recovery(attempts=2, token_cap=1400, token_step=500)
    )
    with pytest.raises(ValueError, match="exhausted 2"):
        asyncio.run(
            consolidate([message("read skill")], Calls(transport, lambda n, d: None), settings)
        )
    assert [request["max_tokens"] for request in transport.requests] == [1200, 1400]


@pytest.mark.parametrize("text,role", [("read  skill", "user"), ("read skill", "assistant")])
def test_repair_does_not_bypass_exact_quote_or_role(text: str, role: str) -> None:
    item = candidate("prompt_act", "unknown", "read skill").model_dump()
    transport = Sequence([invalid("truncated"), chat(json.dumps({"observations": [item]}))])
    result = asyncio.run(
        run_window(
            [message(text, role)], Calls(transport, lambda n, d: None), Settings(baseline=True)
        )
    )
    findings = result["observations"]
    assert isinstance(findings, list)
    assert findings[0]["status"] == "unknown-or-rejected"
    assert findings[0]["probabilities"] == {}
