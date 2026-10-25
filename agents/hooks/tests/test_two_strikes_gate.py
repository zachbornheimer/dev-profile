"""two-strikes-gate.py: cases ported from run.sh, plus sequential
strike-history behavior.

Most cases seed bash/edit/work-order history before the call, and several
fire the SAME fixture repeatedly so history accumulates between calls —
both need hook_harness.HookSession's reused state dir.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from hook_harness import HOOKS_DIR, HookRun, HookRunner, HookSession

PY_HOOK = "two-strikes-gate.py"
STEM = "two-strikes-gate"
DENY = "deny"
ALLOW_SILENT = "none"
EDIT_SEQUENCE_FIXTURE = "two-strikes-edit-seq.json"
WORK_ORDER_SEQUENCE_FIXTURE = "two-strikes-work-order-seq.json"


@dataclass(frozen=True, slots=True)
class FixtureCase:
    fixture: str
    expected: str
    seed: dict[str, list[str]] | None = None


def _case_id(case: FixtureCase) -> str:
    return case.fixture.removesuffix(".json")


FIXTURE_CASES = (
    FixtureCase(
        "two-strikes-bash-repeat-deny.json",
        DENY,
        {
            "bash-history-hgtest-ts-bash-deny.tsv": [
                "1000000000\tgo test ./internal/foo\tfail",
                "1000000001\tgo test ./internal/foo\tfail",
            ]
        },
    ),
    FixtureCase(
        "two-strikes-bash-one-fail-allow.json",
        ALLOW_SILENT,
        {
            "bash-history-hgtest-ts-bash-one.tsv": [
                "1000000000\tgo test ./internal/foo\tfail"
            ]
        },
    ),
    FixtureCase(
        "two-strikes-bash-success-reset-allow.json",
        ALLOW_SILENT,
        {
            "bash-history-hgtest-ts-bash-reset.tsv": [
                "1000000000\tgo test ./internal/foo\tfail",
                "1000000001\tgo test ./internal/foo\tsuccess",
                "1000000002\tgo test ./internal/foo\tfail",
            ]
        },
    ),
    FixtureCase("two-strikes-bash-missing-history-allow.json", ALLOW_SILENT, None),
    FixtureCase("two-strikes-malformed.json", ALLOW_SILENT, None),
    FixtureCase(
        "two-strikes-edit-repeat-deny.json",
        DENY,
        {
            "edit-deny-history-hgtest-ts-edit-deny.tsv": [
                "1000000000\t/tmp/stuck.go\tfail",
                "1000000001\t/tmp/stuck.go\tfail",
            ]
        },
    ),
    FixtureCase(
        "two-strikes-edit-with-progress-allow.json",
        ALLOW_SILENT,
        {
            "edit-deny-history-hgtest-ts-edit-progress.tsv": [
                "1000000000\t/tmp/stuck.go\tfail",
                "1000000001\t/tmp/stuck.go\tfail",
            ],
            "edit-count-hgtest-ts-edit-progress.txt": ["....."],
        },
    ),
    FixtureCase(
        "two-strikes-edit-grok-deny.json",
        DENY,
        {
            "edit-deny-history-hgtest-ts-edit-grok.tsv": [
                "1000000000\t/tmp/stuck.go\tfail",
                "1000000001\t/tmp/stuck.go\tfail",
            ]
        },
    ),
    FixtureCase(
        "two-strikes-work-order-no-agent-allow.json",
        ALLOW_SILENT,
        None,
    ),
)


@pytest.fixture
def state(hooks: HookRunner) -> HookSession:
    return hooks.session(STEM)


def assert_clean_run(run: HookRun) -> None:
    assert run.exit_code == 0
    assert run.stderr == ""
    assert not run.failed_open, run.log


@pytest.mark.parametrize("case", FIXTURE_CASES, ids=_case_id)
def test_port_decides_like_run_sh(state: HookSession, case: FixtureCase) -> None:
    for name, lines in (case.seed or {}).items():
        state.seed(name, lines)

    run = state.run_fixture(PY_HOOK, case.fixture)

    assert_clean_run(run)
    assert run.decision == case.expected, run.stdout


def test_deny_reason_names_debug_protocol(state: HookSession) -> None:
    state.seed(
        "bash-history-hgtest-ts-bash-deny.tsv",
        [
            "1000000000\tgo test ./internal/foo\tfail",
            "1000000001\tgo test ./internal/foo\tfail",
        ],
    )

    run = state.run_fixture(PY_HOOK, "two-strikes-bash-repeat-deny.json")

    assert (
        "debug-protocol" in run.output["hookSpecificOutput"]["permissionDecisionReason"]
    )


def test_edit_deny_reason_names_zys736_not_auto_file(state: HookSession) -> None:
    state.seed(
        "edit-deny-history-hgtest-ts-edit-deny.tsv",
        ["1000000000\t/tmp/stuck.go\tfail", "1000000001\t/tmp/stuck.go\tfail"],
    )

    run = state.run_fixture(PY_HOOK, "two-strikes-edit-repeat-deny.json")

    assert "ZYS-736" in run.output["hookSpecificOutput"]["permissionDecisionReason"]


def test_hook_never_auto_files_linear() -> None:
    text = (HOOKS_DIR / PY_HOOK).read_text()
    assert not any(
        needle in text for needle in ("linear.app", "save_issue", "LINEAR_API")
    )


def test_edit_sequence_third_identical_attempt_denied(state: HookSession) -> None:
    fixture = EDIT_SEQUENCE_FIXTURE

    first = state.run_fixture(PY_HOOK, fixture)
    second = state.run_fixture(PY_HOOK, fixture)
    third = state.run_fixture(PY_HOOK, fixture)

    assert_clean_run(first)
    assert_clean_run(second)
    assert_clean_run(third)
    assert first.decision == ALLOW_SILENT
    assert second.decision == ALLOW_SILENT
    assert third.decision == DENY


def test_work_order_sequence_third_identical_spawn_denied(state: HookSession) -> None:
    fixture = WORK_ORDER_SEQUENCE_FIXTURE

    first = state.run_fixture(PY_HOOK, fixture)
    second = state.run_fixture(PY_HOOK, fixture)
    third = state.run_fixture(PY_HOOK, fixture)

    assert first.decision == ALLOW_SILENT
    assert second.decision == ALLOW_SILENT
    assert third.decision == DENY


def test_no_work_kill_names_zys750(state: HookSession) -> None:
    no_work_sig = "zys750-no-work"
    state.seed(
        "work-order-deny-history-hgtest-ts-wo-nowork.tsv",
        [f"1000000000\t{no_work_sig}\tfail", f"1000000001\t{no_work_sig}\tfail"],
    )

    run = state.run_fixture(
        PY_HOOK,
        "two-strikes-work-order-no-work-deny.json",
        {"HC_SHA256_OVERRIDE": no_work_sig},
    )

    assert "ZYS-750" in run.output["hookSpecificOutput"]["permissionDecisionReason"]


def test_orchestrator_spawns_not_gated(state: HookSession) -> None:
    fixture = "two-strikes-work-order-no-agent-allow.json"
    for _ in range(3):
        run = state.run_fixture(PY_HOOK, fixture)
        assert run.decision == ALLOW_SILENT
