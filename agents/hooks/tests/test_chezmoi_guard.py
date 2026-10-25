"""chezmoi-guard.py: cases ported from the former tests/chezmoi-guard-live-ahead.sh.

Covers this file's CLI and PreToolUse cases, plus the two skill-note
assertions (pointed at their current location under available-skills/).
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest
from hook_harness import HookRun

PY_HOOK = "chezmoi-guard.py"
DENY = "deny"
SILENT = "none"
HOOK_TIMEOUT_SECS = 30
PINNED_NOW_ISO = "2000-01-01T00:00:00Z"

HOOKS_DIR = Path(__file__).resolve().parents[1]
SKILLS_DIR = HOOKS_DIR.parent / "available-skills"

LIVE_AHEAD_PATH = "/tmp/fake-live/hooks/completion-gate.py"

LIVE_AHEAD_REPORT = f"""== live-ahead (1) ==
  {LIVE_AHEAD_PATH}
== in-sync (1) ==
  /tmp/fake-live/AGENTS.md
"""
SOURCE_AHEAD_REPORT = """== source-ahead (1) ==
  /tmp/fake-live/hooks/foo.sh
== in-sync (1) ==
  /tmp/fake-live/AGENTS.md
"""
IN_SYNC_REPORT = """== in-sync (2) ==
  /tmp/fake-live/AGENTS.md
  /tmp/fake-live/hooks/foo.sh
"""

APPLY_PAYLOAD = {
    "session_id": "hgtest-chezmoi-guard",
    "hook_event_name": "PreToolUse",
    "tool_name": "Bash",
    "tool_input": {"command": "chezmoi apply"},
}
OTHER_PAYLOAD = {
    "session_id": "hgtest-chezmoi-guard",
    "hook_event_name": "PreToolUse",
    "tool_name": "Bash",
    "tool_input": {"command": "git status"},
}
MENTION_PAYLOAD = {
    "session_id": "hgtest-chezmoi-guard",
    "hook_event_name": "PreToolUse",
    "tool_name": "Bash",
    "tool_input": {"command": 'echo "never run chezmoi apply"'},
}


def assert_clean_run(run: HookRun) -> None:
    assert run.exit_code == 0
    assert run.stderr == ""
    assert not run.failed_open, run.log


def _report_file(tmp_path: Path, name: str, content: str) -> Path:
    path = tmp_path / name
    path.write_text(content)
    return path


def _fresh_state_dir(tmp_path: Path, label: str) -> Path:
    state_dir = tmp_path / f"state-{label}"
    state_dir.mkdir(parents=True, exist_ok=True)
    return state_dir


def run_cli(
    hook: str, report: Path, state_dir: Path
) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "HC_STATE_DIR_OVERRIDE": str(state_dir),
        "CHEZMOI_DRIFT_REPORT_FILE": str(report),
        "HC_NOW_ISO_OVERRIDE": PINNED_NOW_ISO,
    }
    return subprocess.run(
        [str(HOOKS_DIR / hook), "--check"],
        capture_output=True,
        text=True,
        env=env,
        timeout=HOOK_TIMEOUT_SECS,
        check=False,
    )


def run_hook_payload(
    hook: str, report: Path, payload: dict, state_dir: Path
) -> HookRun:
    env = {
        **os.environ,
        "HC_STATE_DIR_OVERRIDE": str(state_dir),
        "CHEZMOI_DRIFT_REPORT_FILE": str(report),
        "HC_NOW_ISO_OVERRIDE": PINNED_NOW_ISO,
    }
    done = subprocess.run(
        [str(HOOKS_DIR / hook)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
        timeout=HOOK_TIMEOUT_SECS,
        check=False,
    )
    log_path = state_dir / "hooks.log"
    return HookRun(
        done.returncode,
        done.stdout,
        done.stderr,
        log_path.read_text() if log_path.exists() else "",
    )


# --- CLI (--check) -------------------------------------------------------


def test_cli_live_ahead_exits_nonzero_and_names_path(tmp_path: Path) -> None:
    report = _report_file(tmp_path, "live.report", LIVE_AHEAD_REPORT)

    result = run_cli(PY_HOOK, report, _fresh_state_dir(tmp_path, "live"))

    assert result.returncode != 0
    assert LIVE_AHEAD_PATH in result.stderr
    assert "chezmoi re-add" in result.stderr


def test_cli_source_ahead_exits_zero(tmp_path: Path) -> None:
    report = _report_file(tmp_path, "source.report", SOURCE_AHEAD_REPORT)

    result = run_cli(PY_HOOK, report, _fresh_state_dir(tmp_path, "source"))

    assert result.returncode == 0


def test_cli_in_sync_exits_zero(tmp_path: Path) -> None:
    report = _report_file(tmp_path, "sync.report", IN_SYNC_REPORT)

    result = run_cli(PY_HOOK, report, _fresh_state_dir(tmp_path, "sync"))

    assert result.returncode == 0


def test_cli_missing_report_exits_nonzero(tmp_path: Path) -> None:
    result = run_cli(
        PY_HOOK, tmp_path / "missing.report", _fresh_state_dir(tmp_path, "missing")
    )

    assert result.returncode != 0


# --- PreToolUse ------------------------------------------------------------


def test_hook_apply_with_live_ahead_denies_and_names_path(tmp_path: Path) -> None:
    report = _report_file(tmp_path, "live.report", LIVE_AHEAD_REPORT)

    run = run_hook_payload(
        PY_HOOK, report, APPLY_PAYLOAD, _fresh_state_dir(tmp_path, "apply-live")
    )

    assert_clean_run(run)
    assert run.decision == DENY
    assert LIVE_AHEAD_PATH in run.stdout


def test_hook_apply_with_in_sync_allows(tmp_path: Path) -> None:
    report = _report_file(tmp_path, "sync.report", IN_SYNC_REPORT)

    run = run_hook_payload(
        PY_HOOK, report, APPLY_PAYLOAD, _fresh_state_dir(tmp_path, "apply-sync")
    )

    assert_clean_run(run)
    assert run.decision == SILENT


def test_hook_non_apply_command_allows_even_with_live_ahead(tmp_path: Path) -> None:
    report = _report_file(tmp_path, "live.report", LIVE_AHEAD_REPORT)

    run = run_hook_payload(
        PY_HOOK, report, OTHER_PAYLOAD, _fresh_state_dir(tmp_path, "other")
    )

    assert_clean_run(run)
    assert run.decision == SILENT


def test_hook_quoted_mention_of_apply_allows(tmp_path: Path) -> None:
    report = _report_file(tmp_path, "live.report", LIVE_AHEAD_REPORT)

    run = run_hook_payload(
        PY_HOOK, report, MENTION_PAYLOAD, _fresh_state_dir(tmp_path, "mention")
    )

    assert_clean_run(run)
    assert run.decision == SILENT


# --- skill notes: land-ticket / prompt-writer moved to available-skills/ --


@pytest.mark.parametrize("skill", ["land-ticket", "prompt-writer"])
def test_skill_still_documents_chezmoi_guard(skill: str) -> None:
    text = (SKILLS_DIR / skill / "SKILL.md").read_text()

    assert "chezmoi-guard.py" in text
    assert "chezmoi re-add" in text
