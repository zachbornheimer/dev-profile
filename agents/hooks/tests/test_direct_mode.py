"""direct-mode.py: a CLI utility, not a hook -- invoked with argv, not
stdin JSON. Tests run it as a subprocess with HC_STATE_DIR_OVERRIDE pointing
at a scratch dir, and pin file mtimes via HC_FILE_MTIME_OVERRIDE_<sanitized>
so recency comparisons are deterministic.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

from hook_harness import HOOKS_DIR

PY_HOOK = HOOKS_DIR / "direct-mode.py"


def _mtime_override_name(path: Path) -> str:
    return "HC_FILE_MTIME_OVERRIDE_" + re.sub(r"[^A-Za-z0-9_]", "_", str(path))


SESSION_ID_ENV_KEYS = ("GROK_SESSION_ID", "CLAUDE_CODE_SESSION_ID")


def run_cli(
    hook: Path,
    args: list[str],
    state_dir: Path,
    mtimes: dict[Path, int] | None = None,
    extra_env: dict[str, str] | None = None,
):
    env = {**os.environ, "HC_STATE_DIR_OVERRIDE": str(state_dir)}
    for key in SESSION_ID_ENV_KEYS:
        env.pop(key, None)
    env.update(extra_env or {})
    for path, mtime in (mtimes or {}).items():
        env[_mtime_override_name(path)] = str(mtime)
    return subprocess.run(
        [str(hook), *args],
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
        check=False,
    )


def test_usage_error_without_on_or_off(tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    run = run_cli(PY_HOOK, [], state_dir)
    assert run.returncode == 1
    assert "usage" in run.stderr


def test_no_session_state_is_an_error(tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    run = run_cli(PY_HOOK, ["on"], state_dir)
    assert run.returncode == 1
    assert "no session state found" in run.stderr


def test_bogus_arg_still_runs_session_lookup_before_rejecting(tmp_path: Path) -> None:
    # A single unrecognized argument (e.g. "bogus") still runs the session
    # lookup before being rejected, so with no session state present the
    # error is "no session state", not usage.
    state_dir = tmp_path / "state"
    run = run_cli(PY_HOOK, ["bogus"], state_dir)
    assert run.returncode == 1
    assert (
        run.stderr.strip()
        == "direct-mode: no session state found yet — run any Bash/Edit command first, then retry."
    )


def test_picks_newest_session_across_state_families(tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    older = state_dir / "bash-history-hgtest-old.tsv"
    newer = state_dir / "edit-count-hgtest-new.txt"
    older.write_text("x")
    newer.write_text("x")

    run = run_cli(PY_HOOK, ["on"], state_dir, mtimes={older: 100, newer: 200})

    assert run.returncode == 0
    assert "ON for session hgtest-new" in run.stdout
    assert (state_dir / "direct-mode-hgtest-new").exists()


def test_off_removes_the_marker(tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    session_file = state_dir / "agent-spawn-hgtest-off.txt"
    session_file.write_text("x")
    (state_dir / "direct-mode-hgtest-off").touch()

    run = run_cli(PY_HOOK, ["off"], state_dir, mtimes={session_file: 100})

    assert run.returncode == 0
    assert "OFF for session hgtest-off" in run.stdout
    assert not (state_dir / "direct-mode-hgtest-off").exists()


def test_grok_session_id_binds_even_when_newer_state_exists(tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    other = state_dir / "bash-history-hgtest-other.tsv"
    other.write_text("x")

    run = run_cli(
        PY_HOOK,
        ["on"],
        state_dir,
        mtimes={other: 999},
        extra_env={"GROK_SESSION_ID": "sess-grok-live"},
    )

    assert run.returncode == 0
    assert run.stdout.strip() == "direct mode ON for session sess-grok-live"
    assert (state_dir / "direct-mode-sess-grok-live").exists()
    assert not (state_dir / "direct-mode-hgtest-other").exists()


def test_claude_session_id_binds_when_grok_unset(tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    other = state_dir / "bash-history-hgtest-other.tsv"
    other.write_text("x")

    run = run_cli(
        PY_HOOK,
        ["on"],
        state_dir,
        mtimes={other: 999},
        extra_env={"CLAUDE_CODE_SESSION_ID": "sess-claude-live"},
    )

    assert run.returncode == 0
    assert run.stdout.strip() == "direct mode ON for session sess-claude-live"
    assert (state_dir / "direct-mode-sess-claude-live").exists()


def test_grok_session_id_wins_over_claude(tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    state_dir.mkdir()

    run = run_cli(
        PY_HOOK,
        ["on"],
        state_dir,
        extra_env={
            "GROK_SESSION_ID": "sess-grok-live",
            "CLAUDE_CODE_SESSION_ID": "sess-claude-live",
        },
    )

    assert run.returncode == 0
    assert run.stdout.strip() == "direct mode ON for session sess-grok-live"
    assert (state_dir / "direct-mode-sess-grok-live").exists()
    assert not (state_dir / "direct-mode-sess-claude-live").exists()


def test_empty_grok_session_id_falls_through_to_mtime(tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    state_file = state_dir / "bash-history-hgtest-mtime.tsv"
    state_file.write_text("x")

    run = run_cli(
        PY_HOOK,
        ["on"],
        state_dir,
        mtimes={state_file: 100},
        extra_env={"GROK_SESSION_ID": "", "CLAUDE_CODE_SESSION_ID": ""},
    )

    assert run.returncode == 0
    assert "ON for session hgtest-mtime" in run.stdout


def test_off_uses_grok_session_id(tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    (state_dir / "direct-mode-sess-grok-live").touch()
    (state_dir / "direct-mode-hgtest-other").touch()

    run = run_cli(
        PY_HOOK,
        ["off"],
        state_dir,
        extra_env={"GROK_SESSION_ID": "sess-grok-live"},
    )

    assert run.returncode == 0
    assert run.stdout.strip() == "direct mode OFF for session sess-grok-live"
    assert not (state_dir / "direct-mode-sess-grok-live").exists()
    assert (state_dir / "direct-mode-hgtest-other").exists()
