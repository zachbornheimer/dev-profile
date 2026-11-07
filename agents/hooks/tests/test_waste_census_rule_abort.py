"""waste-census must count rule_abort for omp ttsr_injection / rule_violation records (ZYS-2080)."""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

CENSUS = Path(__file__).resolve().parents[1] / "waste-census.py"
spec = importlib.util.spec_from_file_location("waste_census", CENSUS)
assert spec is not None and spec.loader is not None
census_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(census_mod)

# Miniature replay of the rule abort in omp:01a1990d: the injection record sits
# between the interrupted turn and the regained turn. Field shapes copied from
# that session's records (lines 95-97); ids simplified to one parent chain.
SESSION_HEADER = {
    "type": "session",
    "version": 3,
    "id": "01a1990d-7b5e-7554-9b57-43716d787a06",
    "timestamp": "2026-11-01T21:39:20.030Z",
    "cwd": "/home/zbornheimer/Developer/Personal/capability-replicas/mastra",
}
USER_TURN = {
    "type": "message",
    "id": "aa000001",
    "parentId": None,
    "timestamp": "2026-11-01T21:42:24.708Z",
    "runtime": {"version": "18.14.1"},
    "message": {
        "role": "user",
        "content": [{"type": "text", "text": "ship the release notes"}],
    },
}
TTSR_INJECTION = {
    "type": "ttsr_injection",
    "id": "bb000002",
    "parentId": "aa000001",
    "timestamp": "2026-11-01T21:42:57.655Z",
    "runtime": {"version": "18.14.1"},
    "injectedRules": ["pin-landing-policy"],
}
RULE_VIOLATION = {
    "type": "rule_violation",
    "id": "bb000002",
    "parentId": "aa000001",
    "timestamp": "2026-11-01T21:42:57.655Z",
    "runtime": {"version": "18.14.1"},
    "rule": "pin-landing-policy",
}
REGAINED_TURN = {
    "type": "message",
    "id": "cc000003",
    "parentId": "bb000002",
    "timestamp": "2026-11-01T21:43:38.015Z",
    "runtime": {"version": "18.14.1"},
    "message": {
        "role": "assistant",
        "content": [{"type": "text", "text": "Release notes shipped."}],
    },
}


def _write_session(tmp_path: Path, *records: dict) -> Path:
    """Session JSONL: line 1 the header, line 2 the user turn, then records."""
    lines = [SESSION_HEADER, USER_TURN, *records]
    path = tmp_path / "session.jsonl"
    path.write_text("\n".join(json.dumps(line) for line in lines) + "\n")
    return path


def test_ttsr_injection_counts_rule_abort_with_line_id(tmp_path: Path, capsys) -> None:
    path = _write_session(tmp_path, TTSR_INJECTION, REGAINED_TURN)
    findings, _ = census_mod.census(census_mod.load(path))
    assert findings.get("rule_abort") == ["item:3"]
    # An abort is its own class, never folded into the user's recovery.
    assert findings.get("user_recovery", []) == []

    assert census_mod.main(["waste-census.py", str(path)]) == 0
    report = capsys.readouterr().out
    assert re.search(r"^rule_abort\s+1$", report, re.MULTILINE)
    assert "item:3" in report


def test_rule_violation_record_counts_rule_abort(tmp_path: Path) -> None:
    path = _write_session(tmp_path, RULE_VIOLATION, REGAINED_TURN)
    findings, _ = census_mod.census(census_mod.load(path))
    assert findings.get("rule_abort") == ["item:3"]


def test_transcript_without_injections_reports_rule_abort_zero(
    tmp_path: Path, capsys
) -> None:
    path = _write_session(tmp_path, REGAINED_TURN)
    findings, _ = census_mod.census(census_mod.load(path))
    assert findings.get("rule_abort", []) == []

    assert census_mod.main(["waste-census.py", str(path)]) == 0
    report = capsys.readouterr().out
    assert re.search(r"^rule_abort\s+0$", report, re.MULTILINE)
