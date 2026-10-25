"""layout-guard.py: cases ported from the former run.sh."""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from hook_harness import HookRun, HookRunner

PY_HOOK = "layout-guard.py"
DENY = "deny"
SILENT = "none"


@dataclass(frozen=True, slots=True)
class FixtureCase:
    fixture: str
    expected: str
    reason_contains: str | None = None


# One entry per layout-guard expect_* line in tests/run.sh, same order.
FIXTURE_CASES = (
    FixtureCase("layout-bash-mkdir-work-deny.json", DENY, "Canonical destination"),
    FixtureCase("layout-bash-mkdir-developer-allow.json", SILENT),
    FixtureCase("layout-write-llc-path-deny.json", DENY, "Canonical destination"),
    FixtureCase("layout-write-canonical-allow.json", SILENT),
    FixtureCase("layout-bash-clone-desktop-deny.json", DENY, "Canonical destination"),
    FixtureCase("layout-bash-clone-developer-allow.json", SILENT),
    FixtureCase(
        "layout-bash-worktree-wrong-dest-deny.json", DENY, "Canonical destination"
    ),
    FixtureCase("layout-bash-worktree-correct-dest-allow.json", SILENT),
    FixtureCase("layout-malformed-json.json", SILENT),
    FixtureCase("layout-bash-worktree-tilde-detach-canonical-allow.json", SILENT),
    FixtureCase("layout-bash-worktree-home-form-canonical-allow.json", SILENT),
    FixtureCase("layout-bash-worktree-absolute-form-canonical-allow.json", SILENT),
    FixtureCase("layout-bash-worktree-branch-flag-canonical-allow.json", SILENT),
    FixtureCase("layout-bash-worktree-tilde-off-convention-deny.json", DENY),
    FixtureCase("layout-bash-init-desktop-prefix-deny.json", DENY),
    FixtureCase("layout-bash-clone-desktop-prefix-deny.json", DENY),
    FixtureCase("layout-bash-init-dropbox-deny.json", DENY),
    FixtureCase(
        "layout-bash-commit-message-mentions-forbidden-path-allow.json", SILENT
    ),
    FixtureCase(
        "layout-bash-redirection-quoted-sentence-mentioning-target-allow.json", SILENT
    ),
    FixtureCase("layout-bash-redirection-real-target-deny.json", DENY),
)

# Fixtures present on disk but not exercised by run.sh (heredoc-body handling) —
# extra parity coverage, not part of the run.sh-mirroring FIXTURE_CASES above.
EXTRA_FIXTURE_CASES = (
    FixtureCase("layout-bash-heredoc-body-go-import-allow.json", SILENT),
    FixtureCase("layout-bash-heredoc-redirect-target-still-deny.json", DENY),
)


def _case_id(case: FixtureCase) -> str:
    return case.fixture.removesuffix(".json")


def assert_clean_run(run: HookRun) -> None:
    assert run.exit_code == 0
    assert run.stderr == ""
    assert not run.failed_open, run.log


@pytest.mark.parametrize("case", FIXTURE_CASES + EXTRA_FIXTURE_CASES, ids=_case_id)
def test_port_decides_like_run_sh(hooks: HookRunner, case: FixtureCase) -> None:
    run = hooks.run_fixture(PY_HOOK, case.fixture)

    assert_clean_run(run)
    assert run.decision == case.expected, run.stdout
    if case.reason_contains:
        specific = (run.output or {}).get("hookSpecificOutput", {})
        assert case.reason_contains in specific.get("permissionDecisionReason", "")


PAYLOAD_CASES: dict[str, dict] = {
    "grok-camelcase-mkdir-work": {
        "toolName": "run_terminal_command",
        "toolInput": {"command": "mkdir -p ~/work/x"},
    },
    "unrelated-tool-silent": {"tool_name": "Read", "tool_input": {"file_path": "/x"}},
    "empty-command-silent": {"tool_name": "Bash", "tool_input": {"command": ""}},
    "empty-stdin-silent": "",
    "separator-bleed-org-name-after-mkdir": {
        "tool_name": "Bash",
        "tool_input": {
            "command": "mkdir -p /tmp/x && gh repo list Software-Automation-Holdings-LLC --json name"
        },
    },
    "mkdir-after-separator-forbidden": {
        "tool_name": "Bash",
        "tool_input": {"command": "mkdir -p /x && mkdir ~/Developer/Foo-LLC/bar"},
    },
    "mkdir-after-newline-forbidden": {
        "tool_name": "Bash",
        "tool_input": {"command": "mkdir -p /x\nmkdir ~/work"},
    },
    "mkdir-after-semicolon-no-space-forbidden": {
        "tool_name": "Bash",
        "tool_input": {"command": "mkdir -p /x;mkdir ~/work"},
    },
    "mkdir-bare-work-forbidden": {
        "tool_name": "Bash",
        "tool_input": {"command": "mkdir ~/work"},
    },
    "heredoc-commit-message-mentions-worktree-add": {
        "tool_name": "Bash",
        "tool_input": {
            "command": "git commit -F - <<'EOF'\nfeat: deny raw git worktree add in hooks\nEOF"
        },
    },
    "cp-to-forbidden": {
        "tool_name": "Bash",
        "tool_input": {"command": "cp a ~/work/repo"},
    },
    "unmatched-quote-falls-back-to-legacy-tokenize": {
        "tool_name": "Bash",
        "tool_input": {"command": 'mkdir -p ~/work/x"'},
    },
}
PAYLOAD_EXPECTED_DECISION: dict[str, str] = {
    "grok-camelcase-mkdir-work": DENY,
    "unrelated-tool-silent": SILENT,
    "empty-command-silent": SILENT,
    "empty-stdin-silent": SILENT,
    "unmatched-quote-falls-back-to-legacy-tokenize": DENY,
    "separator-bleed-org-name-after-mkdir": SILENT,
    "mkdir-after-separator-forbidden": DENY,
    "mkdir-after-newline-forbidden": DENY,
    "mkdir-after-semicolon-no-space-forbidden": DENY,
    "mkdir-bare-work-forbidden": DENY,
    "cp-to-forbidden": DENY,
    "heredoc-commit-message-mentions-worktree-add": SILENT,
}


@pytest.mark.parametrize("name", PAYLOAD_CASES)
def test_port_decides_on_payload(hooks: HookRunner, name: str) -> None:
    payload = PAYLOAD_CASES[name]
    run = hooks.run_payload(PY_HOOK, payload)
    assert_clean_run(run)
    assert run.decision == PAYLOAD_EXPECTED_DECISION[name], run.stdout
