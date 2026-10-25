"""The judge sees the earlier exchanges, not only the last prompt."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

from completion_gate_transcript import HISTORY_TURNS_KEPT, read_transcript_facts
from completion_gate_turn_evidence import build_envelope


def _user(text: str) -> dict:
    return {"type": "user", "message": {"role": "user", "content": text}}


def _agent(text: str) -> dict:
    return {
        "type": "assistant",
        "message": {"role": "assistant", "content": [{"type": "text", "text": text}]},
    }


def _transcript(tmp_path: Path, records: list[dict]) -> str:
    path = tmp_path / "t.jsonl"
    path.write_text(
        "\n".join(json.dumps(r, separators=(",", ":")) for r in records) + "\n"
    )
    return str(path)


def test_history_holds_earlier_exchanges_oldest_first(tmp_path: Path) -> None:
    path = _transcript(
        tmp_path,
        [
            _user("look at 33eb"),
            _agent("two problems"),
            _user("improve the hook"),
            _agent("found it"),
            _user("go"),
        ],
    )
    facts = read_transcript_facts(path)
    assert facts is not None
    assert facts.user_prompt == "go"
    assert [(t.prompt, t.reply) for t in facts.history] == [
        ("look at 33eb", "two problems"),
        ("improve the hook", "found it"),
    ]


def test_history_keeps_only_the_most_recent_exchanges(tmp_path: Path) -> None:
    records = [
        r
        for i in range(HISTORY_TURNS_KEPT + 3)
        for r in (_user(f"q{i}"), _agent(f"a{i}"))
    ]
    facts = read_transcript_facts(_transcript(tmp_path, [*records, _user("now")]))
    assert facts is not None
    assert len(facts.history) == HISTORY_TURNS_KEPT
    assert facts.history[-1].prompt == f"q{HISTORY_TURNS_KEPT + 2}"


def test_hook_feedback_is_not_an_exchange(tmp_path: Path) -> None:
    facts = read_transcript_facts(
        _transcript(
            tmp_path,
            [
                _user("ask"),
                _agent("reply"),
                _user("Stop hook feedback: do it"),
                _user("next"),
            ],
        )
    )
    assert facts is not None
    assert [t.prompt for t in facts.history] == ["ask"]


def test_envelope_carries_history(tmp_path: Path) -> None:
    facts = read_transcript_facts(
        _transcript(tmp_path, [_user("ask"), _agent("reply"), _user("go")])
    )
    envelope = build_envelope("Done.", facts, {})
    assert envelope["history"] == [{"user_request": "ask", "response": "reply"}]


def test_envelope_without_a_transcript_has_no_history() -> None:
    assert build_envelope("Done.", None, {})["history"] == []


def _tool_round(call_id: str) -> list[dict]:
    use = {
        "type": "tool_use",
        "id": call_id,
        "name": "Bash",
        "input": {"command": "git branch -a"},
    }
    result = {"type": "tool_result", "tool_use_id": call_id, "content": "main"}
    return [
        {"type": "assistant", "message": {"role": "assistant", "content": [use]}},
        {"type": "user", "message": {"role": "user", "content": [result]}},
    ]


def test_interrupt_marker_is_not_a_prompt_and_keeps_the_turn(tmp_path: Path) -> None:
    facts = read_transcript_facts(
        _transcript(
            tmp_path,
            [
                _user("check every branch"),
                *_tool_round("a"),
                _user("[Request interrupted by user]"),
            ],
        )
    )
    assert facts is not None
    assert facts.user_prompt == "check every branch"
    assert [run.command for run in facts.turn_runs] == ["git branch -a"]
