"""waste-census must resolve tool_name from tool_call_id on annotated.json turns exports (ZYS-1906)."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

CENSUS = Path(__file__).resolve().parents[1] / "waste-census.py"
spec = importlib.util.spec_from_file_location("waste_census", CENSUS)
assert spec is not None and spec.loader is not None
census_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(census_mod)

ANNOTATED_OMP_SESSION = (
    Path.home()
    / ".local/share/capability-replicas/annotated"
    / "omp_01a169a2-d468-7000-a856-796b75fda94b.annotated.json"
)


def test_turns_export_resolves_tool_name_from_tool_call_id(tmp_path: Path) -> None:
    export = {
        "turns": [
            {
                "user": [{"id": 1, "text": "check logs"}],
                "response": [
                    {
                        "id": 2,
                        "source": "agent",
                        "text": "Calling write and eval",
                        "tool_calls": [
                            {"id": "call-1", "name": "write", "arguments": {"path": "a.txt"}},
                            {"toolCallId": "call-2", "name": "eval", "arguments": {"code": "1+1"}},
                        ],
                    },
                    {
                        "id": 3,
                        "source": "system",
                        "tool_call_id": "call-1",
                        "content": "Error: permission denied",
                        "is_error": True,
                    },
                    {
                        "id": 4,
                        "source": "system",
                        "toolCallId": "call-2",
                        "tool_name": None,
                        "content": "Traceback: NameError",
                        "is_error": True,
                    },
                ],
            }
        ]
    }
    path = tmp_path / "session.annotated.json"
    path.write_text(json.dumps(export))

    items = census_mod.load(path)
    by_id = {item["id"]: item for item in items}
    assert by_id[3]["tool_name"] == "write"
    assert by_id[4]["tool_name"] == "eval"

    findings = census_mod.census(items)
    assert findings["tool_error"] == ["item:3 (write)", "item:4 (eval)"]


@pytest.mark.skipif(
    not ANNOTATED_OMP_SESSION.is_file(),
    reason="omp_01a169a2 annotated transcript not present on this machine",
)
def test_omp_01a169a2_annotated_transcript_has_no_unknown_tool_errors() -> None:
    items = census_mod.load(ANNOTATED_OMP_SESSION)
    findings = census_mod.census(items)
    tool_errors = findings.get("tool_error", [])
    assert tool_errors, "expected tool_error findings in omp_01a169a2.annotated.json"
    assert "item:36 (write)" in tool_errors
    assert "item:703 (eval)" in tool_errors
    assert not any(entry.endswith("(?)") for entry in tool_errors), (
        f"unresolved tool names remain: {[e for e in tool_errors if e.endswith('(?)')]}"
    )
