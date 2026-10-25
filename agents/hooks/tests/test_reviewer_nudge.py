"""reviewer-nudge.py: cases ported from the former run.sh, including the
dedup sequence, which reuses one state dir across calls via
hook_harness.HookSession.
"""

from __future__ import annotations

import pytest
from hook_harness import HookRun, HookRunner, HookSession

PY_HOOK = "reviewer-nudge.py"
STEM = "reviewer-nudge"
CONTEXT = "context"
SILENT = "none"
DEDUP_FIXTURE = "reviewer-nudge-same-state-second-stop.json"
GROWN_FIXTURE = "reviewer-nudge-state-changed-stop.json"
DEDUP_COUNTER = "edit-count-hgtest-rn3.txt"
FIVE_EDITS = "....."
SEVEN_EDITS = "......."


@pytest.fixture
def state(hooks: HookRunner) -> HookSession:
    return hooks.session(STEM)


def assert_clean_run(run: HookRun) -> None:
    assert run.exit_code == 0
    assert run.stderr == ""
    assert not run.failed_open, run.log


def test_no_review_recorded_nudges(state: HookSession) -> None:
    state.write("edit-count-hgtest-rn1.txt", ".....")

    run = state.run_fixture(PY_HOOK, "reviewer-nudge-no-review.json")

    assert_clean_run(run)
    assert run.decision == CONTEXT


def test_review_recorded_stays_silent(state: HookSession) -> None:
    state.write("edit-count-hgtest-rn2.txt", ".....")
    state.write("agent-spawn-hgtest-rn2.txt", "2026-07-30T00:00:00Z\treviewer\n")

    run = state.run_fixture(PY_HOOK, "reviewer-nudge-review-recorded.json")

    assert_clean_run(run)
    assert run.decision == SILENT


def test_dedup_same_edit_count_only_nudges_once(state: HookSession) -> None:
    state.write(DEDUP_COUNTER, FIVE_EDITS)
    fixture = "reviewer-nudge-same-state-second-stop.json"

    first = state.run_fixture(PY_HOOK, fixture)
    second = state.run_fixture(PY_HOOK, fixture)

    assert_clean_run(first)
    assert_clean_run(second)
    assert first.decision == CONTEXT
    assert second.decision == SILENT


def test_dedup_fires_again_after_edit_count_grows(state: HookSession) -> None:
    state.write(DEDUP_COUNTER, FIVE_EDITS)
    state.run_fixture(PY_HOOK, "reviewer-nudge-same-state-second-stop.json")
    state.write(DEDUP_COUNTER, SEVEN_EDITS)

    run = state.run_fixture(PY_HOOK, "reviewer-nudge-state-changed-stop.json")

    assert_clean_run(run)
    assert run.decision == CONTEXT


def test_malformed_json_fails_open_silently(hooks: HookRunner) -> None:
    run = hooks.run_fixture(PY_HOOK, "reviewer-nudge-malformed.json")

    assert_clean_run(run)
    assert run.decision == SILENT
