"""edit-record.py: cases ported from the former run.sh."""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from hook_harness import HookRunner

PY_HOOK = "edit-record.py"


@dataclass(frozen=True, slots=True)
class FixtureCase:
    fixture: str


FIXTURE_CASES = (
    FixtureCase("edit-record-normal.json"),
    FixtureCase("edit-record-malformed.json"),
)


def _case_id(case: FixtureCase) -> str:
    return case.fixture.removesuffix(".json")


def assert_clean_run(run) -> None:
    assert run.exit_code == 0
    assert run.stderr == ""


@pytest.mark.parametrize("case", FIXTURE_CASES, ids=_case_id)
def test_port_runs_clean(hooks: HookRunner, case: FixtureCase) -> None:
    run = hooks.run_fixture(PY_HOOK, case.fixture)
    assert_clean_run(run)
    assert run.stdout == ""


def test_port_appends_to_session_counter(hooks: HookRunner) -> None:
    hooks.run_fixture(PY_HOOK, "edit-record-normal.json")
    counter = hooks.state_root
    matches = list(counter.glob("edit-record.py-*/edit-count-hgtest-er1.txt"))
    assert matches and matches[0].read_text() == "."


PAYLOAD_CASES: dict[str, dict | str] = {
    "grok-camelcase": {
        "sessionId": "s1",
        "toolName": "search_replace",
        "toolInput": {"file_path": "/x"},
    },
    "no-session-id-silent": {"tool_name": "Edit", "tool_input": {"file_path": "/x"}},
    "empty-stdin-silent": "",
}


@pytest.mark.parametrize("name", PAYLOAD_CASES)
def test_port_runs_clean_on_payload(hooks: HookRunner, name: str) -> None:
    run = hooks.run_payload(PY_HOOK, PAYLOAD_CASES[name])
    assert_clean_run(run)
    assert run.stdout == ""
