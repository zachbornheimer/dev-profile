"""Grok's Stop names its update stream; the judge decodes that stream directly."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

from completion_gate_transcript import read_transcript_facts
from completion_gate_turn_evidence import build_envelope

FIRST_TIMESTAMP = 1_700_000_000
SECOND_TIMESTAMP = 1_700_000_060
SECOND_TIMESTAMP_ISO = "2023-11-14T22:14:20Z"


def _update(kind: str, timestamp: int = FIRST_TIMESTAMP, **fields: object) -> dict:
    return {
        "timestamp": timestamp,
        "method": "_x.ai/session/update",
        "params": {"sessionId": "s", "update": {"sessionUpdate": kind, **fields}},
    }


def _text(kind: str, text: str, timestamp: int = FIRST_TIMESTAMP) -> dict:
    return _update(kind, timestamp, content={"type": "text", "text": text})


def _user(text: str, timestamp: int = FIRST_TIMESTAMP) -> dict:
    return _text("user_message_chunk", text, timestamp)


def _agent(text: str) -> dict:
    return _text("agent_message_chunk", text)


def _call(call_id: str, title: str, command: str) -> dict:
    return _update(
        "tool_call", toolCallId=call_id, title=title, rawInput={"command": command}
    )


def _done(call_id: str, output: str, exit_code: int) -> dict:
    return _update(
        "tool_call_update",
        toolCallId=call_id,
        status="completed",
        rawOutput={"output_for_prompt": output, "exit_code": exit_code},
    )


def _grok_session(tmp_path: Path, records: list[dict]) -> str:
    updates = tmp_path / "updates.jsonl"
    updates.write_text(
        "\n".join(json.dumps(r, separators=(",", ":")) for r in records) + "\n"
    )
    return str(updates)


def test_grok_update_stream_reads_prompt_history_and_commands(tmp_path: Path) -> None:
    path = _grok_session(
        tmp_path,
        [
            _update("agent_thought_chunk"),
            _user("fix the face cap"),
            _call("c1", "run_terminal_command", "pytest -q"),
            _done("c1", "14 passed\n", 0),
            _agent("Fixed; 14 passed."),
            _user("okay, so that's all good now?"),
            _call("c2", "run_terminal_command", "git log -1"),
            _done("c2", "fatal: bad\n", 128),
            _agent("Yes."),
        ],
    )
    facts = read_transcript_facts(path)
    assert facts is not None
    assert facts.user_prompt == "okay, so that's all good now?"
    assert [(t.prompt, t.reply) for t in facts.history] == [
        ("fix the face cap", "Fixed; 14 passed.")
    ]
    assert [(r.tool, r.command, r.failed) for r in facts.turn_runs] == [
        ("Bash", "git log -1", True)
    ]


def test_grok_hook_annotation_is_not_a_prompt(tmp_path: Path) -> None:
    path = _grok_session(
        tmp_path,
        [
            _user("ship it"),
            _agent("Shipped."),
            _text("hook_annotation", "Stop hook feedback: unproven claim"),
            _agent("Here is proof."),
        ],
    )
    facts = read_transcript_facts(path)
    assert facts is not None
    assert facts.user_prompt == "ship it"
    assert facts.history == ()


def test_grok_envelope_carries_user_request_and_history(tmp_path: Path) -> None:
    path = _grok_session(tmp_path, [_user("ask"), _agent("reply"), _user("go")])
    envelope = build_envelope("Done.", read_transcript_facts(path), {})
    assert envelope["user_prompt"] == "go"
    assert envelope["history"] == [{"user_request": "ask", "response": "reply"}]


def test_grok_prompt_carries_its_iso_timestamp(tmp_path: Path) -> None:
    path = _grok_session(tmp_path, [_user("ask"), _user("go", SECOND_TIMESTAMP)])
    facts = read_transcript_facts(path)
    assert facts is not None
    assert facts.prompts[-1].at == SECOND_TIMESTAMP_ISO
