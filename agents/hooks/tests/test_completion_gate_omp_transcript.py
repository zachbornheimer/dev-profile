"""omp's Stop names its session JSONL; the judge decodes that log directly."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

import completion_gate_transcript
from completion_gate_omp_transcript import is_omp_session
from completion_gate_transcript import read_transcript_facts
from completion_gate_turn_evidence import build_envelope

RUN_COMMAND_DEVICE = "xd://mcp__capability_agentmux_capability_run_command"
DEFERRAL = 'Fixed two of six. Reply "go" and I\'ll do those four.'
PROMPT_TIME = "2026-10-26T23:23:32.965Z"


def _row(kind: str, **fields: object) -> dict:
    return {"type": kind, "timestamp": PROMPT_TIME, **fields}


def _message(**message: object) -> dict:
    return _row("message", message=message)


def _user(content: object, attribution: str = "user") -> dict:
    return _message(role="user", content=content, attribution=attribution)


def _assistant(*blocks: dict, stop: str = "stop") -> dict:
    return _message(role="assistant", content=list(blocks), stopReason=stop)


def _text(text: str) -> dict:
    return {"type": "text", "text": text}


def _call(call_id: str, name: str, **arguments: object) -> dict:
    return {"type": "toolCall", "id": call_id, "name": name, "arguments": arguments}


def _result(call_id: str, name: str, output: str, is_error: bool = False) -> dict:
    return _message(
        role="toolResult",
        toolCallId=call_id,
        toolName=name,
        content=[_text(output)],
        isError=is_error,
    )


def _omp_session(tmp_path: Path, records: list[dict]) -> str:
    # omp rewrites a ``title`` row ahead of the ``session`` header.
    header = [
        {"type": "title", "title": "t", "pad": " " * 120},
        _row("session", version=3, id="s", cwd="/tmp"),
    ]
    log = tmp_path / "2026-10-26T23-22-45-006Z_s.jsonl"
    rows = [*header, *records]
    log.write_text("\n".join(json.dumps(r, separators=(",", ":")) for r in rows) + "\n")
    return str(log)


def _deferral_session(tmp_path: Path) -> str:
    return _omp_session(
        tmp_path,
        [
            _row("custom_message", customType="agent-hooks-context", content="hidden"),
            _user("fix the six failing cases"),
            _assistant(
                _text("Fixed; 14 passed."), _call("c0", "bash", command="pytest -q")
            ),
            _result("c0", "bash", "14 passed\n"),
            _user("now the rest of them"),
            _assistant(
                {"type": "thinking", "thinking": "plan"},
                _call(
                    "c1",
                    "write",
                    path=RUN_COMMAND_DEVICE,
                    content='{"command":"git log -1"}',
                ),
                stop="toolUse",
            ),
            _result("c1", "write", "fatal: bad\n", is_error=True),
            _assistant(_text(DEFERRAL)),
        ],
    )


def test_omp_session_reads_prompt_history_and_commands(tmp_path: Path) -> None:
    facts = read_transcript_facts(_deferral_session(tmp_path))
    assert facts is not None
    assert facts.user_prompt == "now the rest of them"
    assert [(t.prompt, t.reply) for t in facts.history] == [
        ("fix the six failing cases", "Fixed; 14 passed.")
    ]
    assert [(r.tool, r.command, r.failed) for r in facts.turn_runs] == [
        ("Bash", "git log -1", True)
    ]
    assert [(r.tool, r.command) for r in facts.runs] == [
        ("Bash", "pytest -q"),
        ("Bash", "git log -1"),
    ]


def test_omp_envelope_carries_user_request_and_history(tmp_path: Path) -> None:
    envelope = build_envelope(
        DEFERRAL, read_transcript_facts(_deferral_session(tmp_path)), {}
    )
    assert envelope["user_prompt"] == "now the rest of them"
    assert envelope["history"] == [
        {"user_request": "fix the six failing cases", "response": "Fixed; 14 passed."}
    ]


def test_omp_session_header_is_found_when_not_the_first_line(tmp_path: Path) -> None:
    assert is_omp_session(Path(_omp_session(tmp_path, [_user("go")])))


def test_non_omp_log_is_not_an_omp_session(tmp_path: Path) -> None:
    claude = tmp_path / "claude.jsonl"
    claude.write_text('{"type":"user","message":{"role":"user","content":"go"}}\n')
    assert not is_omp_session(claude)
    assert not is_omp_session(tmp_path / "missing.jsonl")


def test_omp_injected_and_agent_messages_are_not_prompts(tmp_path: Path) -> None:
    path = _omp_session(
        tmp_path,
        [
            _user("ship it"),
            _assistant(_text("Shipped.")),
            _user("<system-reminder>noise</system-reminder>"),
            _user("Stop hook feedback: unproven claim"),
            _user([_text("subagent assignment")], attribution="agent"),
            _row("custom_message", customType="irc:incoming", content="hello"),
            _assistant(_text("Here is proof.")),
        ],
    )
    facts = read_transcript_facts(path)
    assert facts is not None
    assert facts.user_prompt == "ship it"
    assert facts.history == ()


def test_omp_device_call_accepts_args_omp_already_decoded(tmp_path: Path) -> None:
    """An object-shaped ``content`` used to raise TypeError and fail every Stop hook open.

    The gate reads the whole log, so one such row silenced completion-gate and
    duplicate-turn-breaker for the rest of the session (omp:01a169a2, 2026-10-29).
    """
    path = _omp_session(
        tmp_path,
        [
            _user("check the api"),
            _assistant(
                _call(
                    "c9",
                    "write",
                    path=RUN_COMMAND_DEVICE,
                    content={"command": "echo alive"},
                ),
                stop="toolUse",
            ),
            _result("c9", "write", "alive\n"),
            _assistant(_text("alive")),
        ],
    )
    facts = read_transcript_facts(path)
    assert facts is not None
    assert [(r.tool, r.command) for r in facts.runs] == [("Bash", "echo alive")]


def test_omp_device_call_tolerates_missing_content(tmp_path: Path) -> None:
    path = _omp_session(
        tmp_path,
        [
            _user("check it"),
            _assistant(
                _call("c1", "write", path=RUN_COMMAND_DEVICE, content=None),
                stop="toolUse",
            ),
            _result("c1", "write", "no args\n"),
            _assistant(_text("done")),
        ],
    )
    facts = read_transcript_facts(path)
    assert facts is not None
    assert [(r.tool, r.command) for r in facts.runs] == [("Bash", "")]


def test_omp_prompt_may_be_plain_string_and_carries_its_timestamp(
    tmp_path: Path,
) -> None:
    facts = read_transcript_facts(_omp_session(tmp_path, [_user("ask"), _user("go")]))
    assert facts is not None
    assert facts.user_prompt == "go"
    assert facts.prompts[-1].at == PROMPT_TIME


def test_omp_format_is_detected_from_head_when_tail_read_drops_first_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    padding = [_row("custom", customType="noise", data="x" * 400) for _ in range(20)]
    path = _omp_session(tmp_path, [*padding, _user("ask"), _assistant(_text(DEFERRAL))])
    monkeypatch.setattr(completion_gate_transcript, "TRANSCRIPT_TAIL_BYTES", 2_000)
    assert Path(path).stat().st_size > 2_000
    facts = read_transcript_facts(path)
    assert facts is not None
    assert facts.user_prompt == "ask"
