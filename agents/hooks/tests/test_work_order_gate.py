"""work-order-gate.py: static fixture cases ported from the former run.sh.

The dynamic repair-by-reference flow needs the SAME state dir across two
calls (deny, then a repair resend); HookRunner deliberately gives every
run_payload/run_fixture call a fresh, isolated state dir, so that flow lives
in test_work_order_flows.py instead.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest
from hook_harness import HOOKS_DIR, HookRunner

sys.path.insert(0, str(HOOKS_DIR / "lib"))
from work_order_denials import (
    REQUIRED_FIELDS,
    TRUNCATION_BUDGET,
    fresh_order_reason,
    policy_reason,
    repairable_reason,
)

PY_HOOK = "work-order-gate.py"
ALLOW = "allow"
DENY = "deny"
SILENT = "none"  # a logged allow with no stdout — fork-exempt and legacy-prose-compat


@dataclass(frozen=True, slots=True)
class FixtureCase:
    fixture: str
    expected: str


# One entry per work-order-gate expect_* line in tests/run.sh, same order.
FIXTURE_CASES = (
    FixtureCase("work-order-gate-valid-allow.json", ALLOW),
    FixtureCase("work-order-gate-missing-acceptance-deny.json", DENY),
    FixtureCase("work-order-gate-patched-allow.json", ALLOW),
    FixtureCase("work-order-gate-no-isolation-deny.json", DENY),
    FixtureCase("work-order-gate-atask-workspace-no-isolation-allow.json", ALLOW),
    FixtureCase("work-order-gate-legacy-prose-allow.json", SILENT),
    FixtureCase("work-order-gate-no-fence-deny.json", DENY),
    FixtureCase("work-order-gate-yaml-parse-deny.json", DENY),
    FixtureCase("work-order-gate-spawn-subagent-no-fence-deny.json", DENY),
)

# Fixtures that exist on disk but aren't wired into any tests/run.sh
# expect_* line for this hook (grepped, none found) — likely fixtures for a
# not-yet-shipped compiler normalization feature. Covered for PARITY ONLY
# (both implementations must still agree, whatever the schema currently
# decides), not for a specific allow/deny expectation.
UNLISTED_FIXTURES = (
    "work-order-gate-acceptance-missing-run-deny.json",
    "work-order-gate-empty-primary-targets-deny.json",
    "work-order-gate-normalize-allowed-writes-allow.json",
    "work-order-gate-normalize-empty-expect-array-allow.json",
    "work-order-gate-normalize-legacy-key-allow.json",
    "work-order-gate-normalize-no-fence-tag-allow.json",
)


def _case_id(case: FixtureCase) -> str:
    return case.fixture.removesuffix(".json")


def assert_clean_run(run) -> None:
    assert run.exit_code == 0
    assert run.stderr == ""
    assert not run.failed_open, run.log


@pytest.mark.parametrize("case", FIXTURE_CASES, ids=_case_id)
def test_port_decides_like_run_sh(hooks: HookRunner, case: FixtureCase) -> None:
    run = hooks.run_fixture(PY_HOOK, case.fixture)

    assert_clean_run(run)
    assert run.decision == case.expected, run.stdout


@pytest.mark.parametrize("fixture", UNLISTED_FIXTURES)
def test_port_decides_on_unlisted_fixture(hooks: HookRunner, fixture: str) -> None:
    """These aren't wired to a specific run.sh expectation, just proven not to crash the port."""
    run = hooks.run_fixture(PY_HOOK, fixture)
    assert_clean_run(run)


# --- payload cases the fixtures miss: fork exemption, Grok camelCase, an
# untyped/absent subagent_type, and an unrelated tool.
def _agent(**tool_input) -> dict:
    return {"session_id": "wog-payload", "tool_name": "Agent", "tool_input": tool_input}


PAYLOAD_CASES: dict[str, dict] = {
    "fork-exempt-silent": _agent(
        subagent_type="fork", prompt="anything, no fence needed"
    ),
    "grok-camelcase-subagent-type": {
        "sessionId": "wog-payload",
        "toolName": "spawn_subagent",
        "toolInput": {"subagentType": "fork", "prompt": "anything"},
    },
    "unrelated-tool-silent": {"tool_name": "Read", "tool_input": {"file_path": "/x"}},
    "empty-stdin-silent": "",
}


@pytest.mark.parametrize("name", PAYLOAD_CASES)
def test_port_decides_like_run_sh_on_payload(hooks: HookRunner, name: str) -> None:
    run = hooks.run_payload(PY_HOOK, PAYLOAD_CASES[name])
    assert_clean_run(run)
    assert run.decision == "none"


# --- scope.given: an order may declare already-established facts/artifacts
# the worker must reuse instead of re-deriving. --- standing objective: every
# compiled prompt carries a fixed "ship the acceptance fast" header.
VALID_ORDER_WITH_GIVEN_PROMPT = (
    "```yaml\n"
    "work_order:\n"
    "  schema_version: 1\n"
    '  intent: "Add a clarify feedback field for scoped runner arguments."\n'
    "  scope:\n"
    "    primary_targets:\n"
    "      - README.md\n"
    "    allowed_writes:\n"
    "      - README.md\n"
    "    given:\n"
    '      - "Root cause already found: work-order-compile.py:391 injects the header."\n'
    "  acceptance:\n"
    "    - id: t\n"
    "      kind: command\n"
    "      run: echo hi\n"
    "      expect:\n"
    "        exit_code: 0\n"
    "```\n\nAdd the field."
)


def _valid_order_with_given_payload() -> dict:
    return _agent(
        subagent_type="implement",
        isolation="worktree",
        cwd="/Users/zbornheimer/Developer/Personal/zq",
        prompt=VALID_ORDER_WITH_GIVEN_PROMPT,
    )


def test_order_with_scope_given_is_accepted(hooks: HookRunner) -> None:
    run = hooks.run_payload(PY_HOOK, _valid_order_with_given_payload())

    assert_clean_run(run)
    assert run.decision == ALLOW, run.stdout


def test_compiled_prompt_carries_standing_objective(hooks: HookRunner) -> None:
    run = hooks.run_payload(PY_HOOK, _valid_order_with_given_payload())

    assert_clean_run(run)
    compiled_prompt = run.output["hookSpecificOutput"]["updatedInput"]["prompt"]
    assert (
        "# objective: ship the acceptance with the least wall-clock time and tokens."
        in compiled_prompt
    )


def _reason(run) -> dict:
    return json.loads(run.output["hookSpecificOutput"]["permissionDecisionReason"])


def test_no_fence_deny_is_a_short_pointer_not_a_scaffold(hooks: HookRunner) -> None:
    run = hooks.run_fixture(PY_HOOK, "work-order-gate-no-fence-deny.json")

    assert_clean_run(run)
    body = _reason(run)
    raw = run.output["hookSpecificOutput"]["permissionDecisionReason"]
    assert list(body) == ["order_ref", "missing", "example_path"]
    assert body["missing"] == list(REQUIRED_FIELDS)
    assert len(raw) < TRUNCATION_BUDGET // 2
    assert "```" not in raw
    assert "One sentence" not in raw
    example = Path(body["example_path"]).read_text()
    assert example.startswith("```yaml\n")
    assert "One sentence" not in example
    assert "path/to/file" not in example
    assert "echo hi" not in example
    assert "intent:" in example
    assert "acceptance:" in example


def test_missing_acceptance_example_is_only_that_field(hooks: HookRunner) -> None:
    run = hooks.run_fixture(PY_HOOK, "work-order-gate-missing-acceptance-deny.json")

    assert_clean_run(run)
    body = _reason(run)
    raw = run.output["hookSpecificOutput"]["permissionDecisionReason"]
    assert list(body) == ["order_ref", "missing", "example_path"]
    assert body["missing"] == ["acceptance"]
    assert len(raw) < TRUNCATION_BUDGET // 2
    example = Path(body["example_path"]).read_text()
    assert example.startswith("```work_order_patch\n")
    assert "intent" not in example
    assert "/work_order/acceptance" in example


def test_policy_violation_is_denied_with_its_code_and_message(
    hooks: HookRunner,
) -> None:
    run = hooks.run_fixture(PY_HOOK, "work-order-gate-no-isolation-deny.json")

    assert_clean_run(run)
    body = _reason(run)
    assert list(body) == ["policy"]
    assert body["policy"][0]["code"] == "policy.isolation_required"
    assert body["policy"][0]["message"]
    assert "missing" not in body
    assert "order_ref" not in body


def test_schema_gap_next_to_a_policy_code_still_reports_missing(tmp_path: Path) -> None:
    """A genuine required-field gap keeps the key-names-only repair payload."""
    errors = [
        {
            "path": "/work_order",
            "code": "required",
            "message": "'acceptance' is a required property",
        }
    ]

    body = json.loads(
        repairable_reason(
            "ref", "```yaml\nwork_order: {}\n```", {"errors": errors}, tmp_path
        )
    )

    assert list(body) == ["order_ref", "missing", "example_path"]
    assert body["missing"] == ["acceptance"]


def test_policy_reason_keeps_only_policy_errors() -> None:
    errors = [
        {"path": "/work_order/acceptance", "code": "required", "message": "gap"},
        {
            "path": "/work_order/scope/primary_targets",
            "code": "policy.x",
            "message": "Split it.",
        },
    ]

    assert json.loads(policy_reason(errors)) == {
        "policy": [{"code": "policy.x", "message": "Split it."}]
    }


def test_yaml_parse_error_stays_in_the_file(hooks: HookRunner) -> None:
    run = hooks.run_fixture(PY_HOOK, "work-order-gate-yaml-parse-deny.json")

    assert_clean_run(run)
    body = _reason(run)
    raw = run.output["hookSpecificOutput"]["permissionDecisionReason"]
    assert list(body) == ["missing", "example_path"]
    assert body["missing"] == ["work_order"]
    assert "order_ref" not in body
    assert len(raw) < TRUNCATION_BUDGET // 2
    example = Path(body["example_path"]).read_text()
    assert "mapping values are not allowed here" in example
    assert "One sentence" not in example
    assert example not in raw


def test_long_example_file_stays_out_of_the_deny_payload(tmp_path: Path) -> None:
    """The reason stays well under Grok's ~1KB end-truncation even if the file is huge."""
    long = "mapping " + ("x" * 20_000)
    reason = fresh_order_reason(
        "prompt with a broken fence",
        {
            "errors": [
                {"path": "/work_order", "code": "yaml_parse_error", "message": long}
            ]
        },
        tmp_path,
    )

    assert len(reason) < TRUNCATION_BUDGET // 2
    assert long not in reason
    assert "x" * 80 not in reason
    body = json.loads(reason)
    assert list(body) == ["missing", "example_path"]
    assert long in Path(body["example_path"]).read_text()
