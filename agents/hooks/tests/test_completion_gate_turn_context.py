"""The judge is told whether the turn acted, and a block names the claim it judged."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

from completion_gate_evidence import EvidenceClaim
from completion_gate_transcript import read_transcript_facts
from completion_gate_turn_evidence import build_digest
from completion_gate_turn_judge import TurnJudgment, block_reason


def _user(text: str) -> dict:
    return {"type": "user", "message": {"role": "user", "content": text}}


def _round(call_id: str, tool: str, args: dict) -> list[dict]:
    use = {"type": "tool_use", "id": call_id, "name": tool, "input": args}
    result = {"type": "tool_result", "tool_use_id": call_id, "content": "ok"}
    return [
        {"type": "assistant", "message": {"role": "assistant", "content": [use]}},
        {"type": "user", "message": {"role": "user", "content": [result]}},
    ]


def _digest(tmp_path: Path, records: list[dict]) -> dict:
    path = tmp_path / "t.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n")
    return build_digest(read_transcript_facts(str(path)), EvidenceClaim(present=False))


def test_a_turn_of_only_reads_is_read_only(tmp_path: Path) -> None:
    digest = _digest(
        tmp_path,
        [
            _user("what does this do"),
            *_round("a", "Read", {"file_path": "x"}),
            *_round("b", "Grep", {"pattern": "y"}),
        ],
    )
    assert digest["turn_type"] == "read_only"
    assert digest["acting_tools_this_turn"] == []


def test_a_shell_call_makes_the_turn_acted(tmp_path: Path) -> None:
    digest = _digest(
        tmp_path,
        [
            _user("fix it"),
            *_round("a", "Read", {"file_path": "x"}),
            *_round("b", "Bash", {"command": "git status"}),
            *_round("c", "Edit", {"file_path": "x"}),
            *_round("d", "Bash", {"command": "mise run test"}),
        ],
    )
    assert digest["turn_type"] == "acted"
    assert digest["acting_tools_this_turn"] == ["Bash", "Edit"]


def test_a_tool_outside_the_read_list_counts_as_acting(tmp_path: Path) -> None:
    digest = _digest(tmp_path, [_user("go"), *_round("a", "SomeNewTool", {"x": 1})])
    assert digest["turn_type"] == "acted"


def test_unproven_claim_block_quotes_the_claim() -> None:
    judgment = TurnJudgment(
        verdict={"action": "block", "block_kind": "unproven_claim", "signals": {}}
    )
    reason = block_reason(
        judgment, "Checked.\n\nAll 40 tests pass.", evidence_problem=""
    )
    assert reason.startswith('You closed with: "All 40 tests pass."')
    assert "unproven claim" in reason
