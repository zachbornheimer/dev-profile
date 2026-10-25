"""gate-bypass-tripwire.py: cases ported from the former run.sh.

FIXTURE_CASES mirrors the hook's expect_deny / expect_allow lines from the
former tests/run.sh one-for-one.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from hook_harness import FIXTURES_DIR, HookRun, HookRunner

PY_HOOK = "gate-bypass-tripwire.py"
DENY = "deny"
SILENT = "none"


@dataclass(frozen=True, slots=True)
class FixtureCase:
    fixture: str
    expected: str


# One entry per tripwire expect_* line in tests/run.sh, same order.
FIXTURE_CASES = (
    FixtureCase("tripwire-bash-no-verify-deny.json", DENY),
    FixtureCase("tripwire-bash-no-verify-allow.json", SILENT),
    FixtureCase("tripwire-bash-force-push-main-deny.json", DENY),
    FixtureCase("tripwire-bash-force-push-feature-allow.json", SILENT),
    FixtureCase("tripwire-bash-lockfile-sed-deny.json", DENY),
    FixtureCase("tripwire-bash-sed-other-file-allow.json", SILENT),
    FixtureCase("tripwire-edit-add-pragma-deny.json", DENY),
    FixtureCase("tripwire-edit-no-pragma-allow.json", SILENT),
    FixtureCase("tripwire-write-generated-path-deny.json", DENY),
    FixtureCase("tripwire-write-dotted-generated-deny.json", DENY),
    FixtureCase("tripwire-write-dotted-gen-deny.json", DENY),
    FixtureCase("tripwire-write-near-miss-genesis-allow.json", SILENT),
    FixtureCase("tripwire-write-near-miss-general-allow.json", SILENT),
    FixtureCase("tripwire-malformed-json.json", SILENT),
    FixtureCase("tripwire-bash-commit-short-no-verify-deny.json", DENY),
    FixtureCase("tripwire-bash-force-push-head-deny.json", DENY),
    FixtureCase("tripwire-bash-force-push-bare-deny.json", DENY),
    FixtureCase("tripwire-bash-perl-pi-lockfile-deny.json", DENY),
    FixtureCase("tripwire-bash-quoted-trigger-text-allow.json", SILENT),
    FixtureCase("tripwire-bash-commit-short-no-verify-compound-and-deny.json", DENY),
    FixtureCase("tripwire-bash-force-push-head-compound-semicolon-deny.json", DENY),
    FixtureCase("tripwire-bash-perl-pi-lockfile-compound-and-deny.json", DENY),
    FixtureCase("tripwire-bash-compound-allowed-atoms-allow.json", SILENT),
    FixtureCase("tripwire-bash-quoted-no-verify-flag-deny.json", DENY),
    FixtureCase("tripwire-bash-quoted-force-push-main-deny.json", DENY),
    FixtureCase("tripwire-bash-quoted-sed-i-lockfile-deny.json", DENY),
    FixtureCase("tripwire-bash-cmdsub-dollar-paren-no-verify-deny.json", DENY),
    FixtureCase("tripwire-bash-cmdsub-backtick-no-verify-deny.json", DENY),
    FixtureCase("tripwire-bash-hookspath-bypass-separate-tokens-deny.json", DENY),
    FixtureCase("tripwire-bash-hookspath-bypass-glued-token-deny.json", DENY),
    FixtureCase("tripwire-bash-benign-c-flag-allow.json", SILENT),
)


def _case_id(case: FixtureCase) -> str:
    return case.fixture.removesuffix(".json")


def assert_clean_run(run: HookRun) -> None:
    """A hook that crashed and failed open would 'pass' every allow case."""
    assert run.exit_code == 0
    assert run.stderr == ""
    assert not run.failed_open, run.log


@pytest.mark.parametrize("case", FIXTURE_CASES, ids=_case_id)
def test_port_decides_like_run_sh(hooks: HookRunner, case: FixtureCase) -> None:
    run = hooks.run_fixture(PY_HOOK, case.fixture)

    assert_clean_run(run)
    assert run.decision == case.expected, run.stdout


# Content that adds a pragma, taken from the Edit fixture rather than restated here.
PRAGMA_LINE_CONTENT = json.loads(
    (FIXTURES_DIR / "tripwire-edit-add-pragma-deny.json").read_text()
)["tool_input"]["new_string"]


def _write(path: Path, content: str) -> dict[str, Any]:
    return {
        "tool_name": "Write",
        "tool_input": {"file_path": str(path), "content": content},
    }


def _bash(command: str) -> dict[str, Any]:
    return {"tool_name": "Bash", "tool_input": {"command": command}}


def _write_over_file_with_pragma(tmp: Path) -> dict[str, Any]:
    existing = tmp / "kept.ts"
    existing.write_text(PRAGMA_LINE_CONTENT)
    return _write(existing, PRAGMA_LINE_CONTENT)


def _write_adding_pragma_to_file(tmp: Path) -> dict[str, Any]:
    existing = tmp / "clean.ts"
    existing.write_text("const x = 1;")
    return _write(existing, PRAGMA_LINE_CONTENT)


# Inputs the fixtures don't cover: the Write disk read, Grok field names,
# unparseable quoting (text layer alone), and silent paths.
PayloadFactory = Callable[[Path], "dict[str, Any] | str"]
PAYLOAD_CASES: dict[str, PayloadFactory] = {
    "write-keeps-existing-pragma": _write_over_file_with_pragma,
    "write-adds-pragma-to-existing-file": _write_adding_pragma_to_file,
    "write-new-file-with-pragma": lambda tmp: _write(
        tmp / "new.ts", PRAGMA_LINE_CONTENT
    ),
    "grok-camelcase-force-push": lambda _tmp: {
        "toolName": "run_terminal_command",
        "toolInput": {"command": "git push -f origin main"},
    },
    "unmatched-quote-falls-back-to-text": lambda _tmp: _bash(
        'git commit -m "wip --no-verify'
    ),
    # Replicated latent false positive: the text layer is not segment-aware.
    "text-layer-short-n-across-and": lambda _tmp: _bash(
        "git commit -m x && echo -n hi"
    ),
    "unrelated-tool-silent": lambda _tmp: {
        "tool_name": "Read",
        "tool_input": {"file_path": "/x"},
    },
    "empty-command-silent": lambda _tmp: _bash(""),
    "empty-stdin-silent": lambda _tmp: "",
}


PAYLOAD_EXPECTED_DECISION: dict[str, str] = {
    "write-keeps-existing-pragma": SILENT,
    "write-adds-pragma-to-existing-file": DENY,
    "write-new-file-with-pragma": DENY,
    "grok-camelcase-force-push": DENY,
    "unmatched-quote-falls-back-to-text": DENY,
    "text-layer-short-n-across-and": DENY,
    "unrelated-tool-silent": SILENT,
    "empty-command-silent": SILENT,
    "empty-stdin-silent": SILENT,
}


@pytest.mark.parametrize("name", PAYLOAD_CASES)
def test_port_decides_on_payload(hooks: HookRunner, tmp_path: Path, name: str) -> None:
    payload = PAYLOAD_CASES[name](tmp_path)

    run = hooks.run_payload(PY_HOOK, payload)

    assert_clean_run(run)
    assert run.decision == PAYLOAD_EXPECTED_DECISION[name], run.stdout
