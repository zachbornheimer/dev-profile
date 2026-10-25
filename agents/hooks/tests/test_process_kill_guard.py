"""process-kill-guard.py: no worker may kill `wt` (worktrunk) processes, and
unscoped `pkill -f` must go through the age-limited `pkill-aged` wrapper.

Commands are parsed or sent as hook payloads; only the pkill-aged tests signal anything,
and only a decoy `sleep` this file spawned.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from hook_harness import FIXTURES_DIR, HOOKS_DIR, HookRun, HookRunner

sys.path.insert(0, str(HOOKS_DIR / "lib"))

from command_words import simple_commands
from process_kill_rules import deny_reason

sys.path.insert(0, str(FIXTURES_DIR))

from process_kill_cases import CASES, DENY, SILENT, WRAPPER, Case

HOOK = "process-kill-guard.py"
REPO_CWD = "/Users/zbornheimer/Developer/Personal/zq"
OVERRIDE_ENV = "ALLOW_UNSAFE_PKILL"
WRAPPER_PATH = Path(__file__).resolve().parents[2] / "bin" / WRAPPER
DECOY_AGE_FLOOR_SECONDS = 1
DECOY_SETTLE_SECONDS = 2.2
DECOY_EXIT_WAIT_SECONDS = 5


HOOK_PROCESS_CASES = frozenset(
    {
        "wt-step-commit-deny",
        "wt-regex-deny",
        "pkill-f-vite-deny",
        "wrapper-vite-allow",
        "unrelated-allow",
    }
)


def _case_id(case: Case) -> str:
    return case.name


def payload(command: str, **extra: object) -> dict:
    return {
        "tool_name": "Bash",
        "tool_input": {"command": command},
        "cwd": REPO_CWD,
        **extra,
    }


def assert_clean_run(run: HookRun) -> None:
    assert run.exit_code == 0
    assert run.stderr == ""
    assert not run.failed_open, run.log


def rule_verdict(command: str) -> str:
    """The rules' own verdict, in-process: the table is large, a hook launch is not free."""
    return DENY if deny_reason(simple_commands(command), command) else SILENT


@pytest.mark.parametrize("case", CASES, ids=_case_id)
def test_process_kill_rules(case: Case, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(OVERRIDE_ENV, raising=False)
    assert rule_verdict(case.command) == case.expected


@pytest.mark.parametrize(
    "case",
    [case for case in CASES if case.name in HOOK_PROCESS_CASES],
    ids=_case_id,
)
def test_process_kill_guard_hook_process(hooks: HookRunner, case: Case) -> None:
    run = hooks.run_payload(HOOK, payload(case.command))
    assert_clean_run(run)
    assert run.decision == case.expected, run.log


def deny_message(run: HookRun) -> str:
    return run.output["hookSpecificOutput"]["permissionDecisionReason"]


def test_wt_denial_names_cause_wrapper_and_override(hooks: HookRunner) -> None:
    message = deny_message(
        hooks.run_payload(HOOK, payload('pkill -f "wt step commit"'))
    )
    assert "commit" in message
    assert WRAPPER in message
    assert OVERRIDE_ENV in message


def test_broad_denial_names_wrapper_and_missing_flag_and_override(
    hooks: HookRunner,
) -> None:
    message = deny_message(hooks.run_payload(HOOK, payload("pkill -f vite")))
    assert WRAPPER in message
    assert "-O" in message
    assert OVERRIDE_ENV in message


# --- Override: honored only when set deliberately, with a reason ----------


@pytest.mark.parametrize(
    "command",
    (
        "ALLOW_UNSAFE_PKILL='stuck wt holding a lock' pkill -f wt",
        "ALLOW_UNSAFE_PKILL=orphaned-vite pkill -f vite",
        "ALLOW_UNSAFE_PKILL=1 pkill -f vite",
        "echo go; ALLOW_UNSAFE_PKILL=reason pgrep -f wt | xargs kill",
    ),
    ids=("wt-reason", "broad-reason", "flag-one", "after-separator"),
)
def test_inline_override_allows(command: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(OVERRIDE_ENV, raising=False)
    assert rule_verdict(command) == SILENT


@pytest.mark.parametrize(
    "command",
    (
        "ALLOW_UNSAFE_PKILL= pkill -f wt",
        "ALLOW_UNSAFE_PKILL=0 pkill -f wt",
        "ALLOW_UNSAFE_PKILL=false pkill -f vite",
    ),
    ids=("empty", "zero", "false"),
)
def test_empty_or_disabled_override_still_denies(
    command: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(OVERRIDE_ENV, raising=False)
    assert rule_verdict(command) == DENY


def test_override_in_hook_environment_allows(hooks: HookRunner) -> None:
    session = hooks.session(HOOK, env={OVERRIDE_ENV: "deliberate"})
    run = session.run_payload(HOOK, payload("pkill -f wt"))
    assert_clean_run(run)
    assert run.decision == SILENT, run.log


# --- Fail-open and harness payload shapes ----------------------------------


def test_malformed_json_fails_open(hooks: HookRunner) -> None:
    run = hooks.run_payload(HOOK, "{not json")
    assert run.exit_code == 0
    assert run.decision == SILENT


def test_non_bash_tool_is_untouched(hooks: HookRunner) -> None:
    run = hooks.run_payload(
        HOOK, {"tool_name": "Edit", "tool_input": {"file_path": "/tmp/x"}}
    )
    assert_clean_run(run)
    assert run.decision == SILENT


def test_subagent_call_is_still_denied(hooks: HookRunner) -> None:
    """Unlike orchestrator-only, workers (agent_id present) are the target."""
    run = hooks.run_payload(HOOK, payload("pkill -f wt", agent_id="agent-1"))
    assert_clean_run(run)
    assert run.decision == DENY, run.log


def test_grok_camelcase_payload_denied(hooks: HookRunner) -> None:
    grok = {
        "hookEventName": "pre_tool_use",
        "toolName": "run_terminal_command",
        "toolInput": {"command": 'pkill -f "wt step commit"'},
        "cwd": REPO_CWD,
    }
    run = hooks.run_payload(HOOK, grok)
    assert_clean_run(run)
    assert run.decision == DENY, run.log


def test_grok_camelcase_payload_allows_wrapper(hooks: HookRunner) -> None:
    grok = {
        "hookEventName": "pre_tool_use",
        "toolName": "run_terminal_command",
        "toolInput": {"command": f"{WRAPPER} -f vite"},
        "cwd": REPO_CWD,
    }
    run = hooks.run_payload(HOOK, grok)
    assert_clean_run(run)
    assert run.decision == SILENT, run.log


# --- pkill-aged: signals only processes older than the age floor ----------


@pytest.fixture
def decoy() -> Iterator[subprocess.Popen]:
    """A long `sleep` with a pattern no other process carries; killed by exact PID."""
    marker = f"1000.{os.getpid()}{time.time_ns()}"
    process = subprocess.Popen(["sleep", marker])
    process.marker = marker  # type: ignore[attr-defined]
    yield process
    process.kill()
    process.wait()


def run_wrapper(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(WRAPPER_PATH), *args], capture_output=True, text=True, check=False
    )


def test_wrapper_spares_a_process_younger_than_the_default_floor(
    decoy: subprocess.Popen,
) -> None:
    done = run_wrapper("-f", decoy.marker)
    assert decoy.poll() is None, done.stderr
    assert done.returncode == 1


def test_wrapper_signals_a_process_older_than_the_floor(
    decoy: subprocess.Popen,
) -> None:
    time.sleep(DECOY_SETTLE_SECONDS)
    done = run_wrapper("-O", str(DECOY_AGE_FLOOR_SECONDS), "-f", decoy.marker)
    assert decoy.wait(timeout=DECOY_EXIT_WAIT_SECONDS) is not None, done.stderr
    assert done.returncode == 0


def test_wrapper_rejects_a_missing_pattern() -> None:
    assert run_wrapper("-f").returncode == 2
