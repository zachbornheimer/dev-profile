"""agent-spawn-record.py: cases ported from the former run.sh."""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from hook_harness import HookRunner

PY_HOOK = "agent-spawn-record.py"


@dataclass(frozen=True, slots=True)
class FixtureCase:
    fixture: str


FIXTURE_CASES = (
    FixtureCase("agent-spawn-record-normal.json"),
    FixtureCase("agent-spawn-record-malformed.json"),
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
