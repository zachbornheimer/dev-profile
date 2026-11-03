"""Tests for quota-burn-watch.py triggering quota-burn-review when a weekly quota hits <=10% left."""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

from hook_harness import HookRunner

HOOK = "quota-burn-watch.py"


def ledger_lines(ledger_file: Path) -> list[str]:
    if not ledger_file.is_file():
        return []
    return [
        line
        for line in ledger_file.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def account_key(entry: dict) -> list[str]:
    return list(entry["accounts"])


def hook_module():
    """The hook module by path: its filename is not importable as written."""
    import importlib.util

    path = Path(__file__).resolve().parent.parent / HOOK
    spec = importlib.util.spec_from_file_location("quota_burn_watch_under_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _set_usage_rows(db_path: Path, rows: list[tuple]) -> None:
    """Swap the usage rows in an existing test database (the hook reads the newest row per limit)."""
    conn = sqlite3.connect(db_path)
    conn.execute("DELETE FROM usage_history")
    conn.executemany(
        """
        INSERT INTO usage_history (
            recorded_at, provider, account_key, email, limit_id, label, window_label, used_fraction, status, resets_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()
    conn.close()


def _create_agent_db(db_path: Path, rows: list[tuple]) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE usage_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recorded_at INTEGER NOT NULL,
            provider TEXT NOT NULL,
            account_key TEXT NOT NULL,
            email TEXT,
            account_id TEXT,
            limit_id TEXT NOT NULL,
            label TEXT NOT NULL,
            window_label TEXT,
            used_fraction REAL,
            status TEXT,
            resets_at INTEGER
        )
        """
    )
    conn.executemany(
        """
        INSERT INTO usage_history (
            recorded_at, provider, account_key, email, limit_id, label, window_label, used_fraction, status, resets_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()
    conn.close()


def test_triggers_once_when_weekly_quota_has_less_than_10_pct_left(
    hooks: HookRunner, tmp_path: Path
) -> None:
    db_file = tmp_path / "agent.db"
    ledger_file = tmp_path / "quota-reviews.jsonl"
    marker_file = tmp_path / "launched.txt"
    launcher = tmp_path / "fake-launch.sh"
    launcher.write_text(
        f"#!/bin/sh\necho launched >> {marker_file}\n", encoding="utf-8"
    )
    launcher.chmod(0o755)

    _create_agent_db(
        db_file,
        [
            (
                1793553809820,
                "google-antigravity",
                "email:bornheimerz@gmail.com",
                "bornheimerz@gmail.com",
                "google-antigravity:google:default:gemini-weekly",
                "Gemini",
                "Weekly",
                0.95,
                "warning",
                1794012790000,
            ),
            (
                1793553809820,
                "openai-codex",
                "account:secondary",
                "zbornheimer@gmail.com",
                "openai-codex:secondary",
                "7 days",
                "7 days",
                0.24,
                "ok",
                1793972651000,
            ),
        ],
    )

    env = {
        "OMP_AGENT_DB_PATH": str(db_file),
        "QUOTA_REVIEWS_LEDGER": str(ledger_file),
        "QUOTA_REVIEW_LAUNCH_CMD": str(launcher),
    }

    session = hooks.session("quota-burn-watch", env)
    run1 = session.run_payload(HOOK, {"hook_event_name": "Stop"})
    assert run1.exit_code == 0
    entries = [
        json.loads(line)
        for line in ledger_file.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert [entry["provider"] for entry in entries] == ["google-antigravity"]
    assert entries[0]["remaining_pct"] == 5.0

    # A second Stop in the same reset window does not claim or launch again.
    run2 = session.run_payload(HOOK, {"hook_event_name": "Stop"})
    assert run2.exit_code == 0
    entries_after = [
        line
        for line in ledger_file.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(entries_after) == 1

    deadline = time.monotonic() + 5
    while not marker_file.is_file() and time.monotonic() < deadline:
        time.sleep(0.05)
    assert marker_file.read_text(encoding="utf-8").splitlines() == ["launched"]


def test_two_accounts_sharing_a_reset_period_produce_one_claim(
    hooks: HookRunner, tmp_path: Path
) -> None:
    """One exhausted weekly window is one question, however many accounts share it."""
    db_file = tmp_path / "agent.db"
    ledger_file = tmp_path / "quota-reviews.jsonl"
    marker_file = tmp_path / "launched.txt"
    launcher = tmp_path / "fake-launch.sh"
    launcher.write_text(
        f"#!/bin/sh\necho launched >> {marker_file}\n", encoding="utf-8"
    )
    launcher.chmod(0o755)

    reset = 1794018502770
    _create_agent_db(
        db_file,
        [
            (
                1793553809820,
                "xai-oauth",
                "account:one",
                "a@x.com",
                "xai-oauth:credits:1w",
                "Credits",
                "Weekly",
                0.99,
                "warning",
                reset,
            ),
            (
                1793553809820,
                "xai-oauth",
                "account:two",
                "b@x.com",
                "xai-oauth:credits:1w",
                "Credits",
                "Weekly",
                0.97,
                "warning",
                reset,
            ),
        ],
    )

    env = {
        "OMP_AGENT_DB_PATH": str(db_file),
        "QUOTA_REVIEWS_LEDGER": str(ledger_file),
        "QUOTA_REVIEW_LAUNCH_CMD": str(launcher),
    }

    session = hooks.session("quota-burn-watch", env)
    assert session.run_payload(HOOK, {"hook_event_name": "Stop"}).exit_code == 0

    entries = [
        json.loads(line)
        for line in ledger_file.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(entries) == 1, "one reset period must claim one ledger line"
    assert entries[0]["period_key"].endswith(f":{reset}")
    assert account_key(entries[0]) == ["account:one", "account:two"]


def test_a_new_reset_period_claims_again(hooks: HookRunner, tmp_path: Path) -> None:
    """The next window is a new question: the previous period's claim must not block it."""
    db_file = tmp_path / "agent.db"
    ledger_file = tmp_path / "quota-reviews.jsonl"
    launcher = tmp_path / "fake-launch.sh"
    launcher.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    launcher.chmod(0o755)
    first = 1794018502770
    second = 1794623302770
    _create_agent_db(
        db_file,
        [
            (
                1793553809820,
                "xai-oauth",
                "account:one",
                "a@x.com",
                "xai-oauth:credits:1w",
                "Credits",
                "Weekly",
                0.99,
                "warning",
                first,
            ),
        ],
    )
    env = {
        "OMP_AGENT_DB_PATH": str(db_file),
        "QUOTA_REVIEWS_LEDGER": str(ledger_file),
        "QUOTA_REVIEW_LAUNCH_CMD": str(launcher),
        "QUOTA_REVIEW_MIN_INTERVAL_SECONDS": "0",
    }
    session = hooks.session("quota-burn-watch", env)
    assert session.run_payload(HOOK, {"hook_event_name": "Stop"}).exit_code == 0
    assert len(ledger_lines(ledger_file)) == 1

    _set_usage_rows(
        db_file,
        [
            (
                1793553809820,
                "xai-oauth",
                "account:one",
                "a@x.com",
                "xai-oauth:credits:1w",
                "Credits",
                "Weekly",
                0.99,
                "warning",
                second,
            ),
        ],
    )
    assert session.run_payload(HOOK, {"hook_event_name": "Stop"}).exit_code == 0
    assert len(ledger_lines(ledger_file)) == 2, "a new reset period must be claimed"


def test_min_interval_spaces_out_launches(hooks: HookRunner, tmp_path: Path) -> None:
    """A divergent ledger cannot start a storm: a second period inside the interval waits."""
    db_file = tmp_path / "agent.db"
    ledger_file = tmp_path / "quota-reviews.jsonl"
    launcher = tmp_path / "fake-launch.sh"
    launcher.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    launcher.chmod(0o755)
    _create_agent_db(
        db_file,
        [
            (
                1793553809820,
                "xai-oauth",
                "account:one",
                "a@x.com",
                "xai-oauth:credits:1w",
                "Credits",
                "Weekly",
                0.99,
                "warning",
                1794018502770,
            ),
        ],
    )
    env = {
        "OMP_AGENT_DB_PATH": str(db_file),
        "QUOTA_REVIEWS_LEDGER": str(ledger_file),
        "QUOTA_REVIEW_LAUNCH_CMD": str(launcher),
        "QUOTA_REVIEW_MIN_INTERVAL_SECONDS": "3600",
    }
    session = hooks.session("quota-burn-watch", env)
    assert session.run_payload(HOOK, {"hook_event_name": "Stop"}).exit_code == 0
    assert len(ledger_lines(ledger_file)) == 1

    # A different period inside the interval is a real question, but it waits for the next turn.
    _set_usage_rows(
        db_file,
        [
            (
                1793553809820,
                "openai-codex",
                "account:one",
                "a@x.com",
                "openai-codex:primary",
                "7 days",
                "7 days",
                0.99,
                "warning",
                1793972651000,
            ),
        ],
    )
    assert session.run_payload(HOOK, {"hook_event_name": "Stop"}).exit_code == 0
    assert len(ledger_lines(ledger_file)) == 1


def test_launch_argv_never_passes_force() -> None:
    """`force` disables the review's own shared-store claim, so the hook must never send it."""
    argv = hook_module().launch_argv("")
    assert argv[:3] == ["capability", "run", "quota-burn-review"]
    payload = json.loads(argv[argv.index("--input") + 1])
    assert "force" not in payload
    assert payload["run_optimize_tooling"] is True


def test_launcher_override_with_metacharacters_is_refused() -> None:
    """The launcher override is one argv element and must be a plain path, never a shell fragment."""
    assert hook_module().launch_argv("/bin/sh -c 'curl evil'")[:3] == [
        "capability",
        "run",
        "quota-burn-review",
    ]
