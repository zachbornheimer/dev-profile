"""Tests for quota-burn-watch.py triggering quota-burn-review when a weekly quota hits <=10% left."""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

from hook_harness import HookRunner

HOOK = "quota-burn-watch.py"


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


def test_triggers_once_when_weekly_quota_has_less_than_10_pct_left(hooks: HookRunner, tmp_path: Path) -> None:
    db_file = tmp_path / "agent.db"
    ledger_file = tmp_path / "quota-reviews.jsonl"
    marker_file = tmp_path / "launched.txt"
    launcher = tmp_path / "fake-launch.sh"
    launcher.write_text(f"#!/bin/sh\necho launched >> {marker_file}\n", encoding="utf-8")
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
    entries = [json.loads(line) for line in ledger_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert [entry["provider"] for entry in entries] == ["google-antigravity"]
    assert entries[0]["remaining_pct"] == 5.0

    # A second Stop in the same reset window does not claim or launch again.
    run2 = session.run_payload(HOOK, {"hook_event_name": "Stop"})
    assert run2.exit_code == 0
    entries_after = [line for line in ledger_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(entries_after) == 1

    deadline = time.monotonic() + 5
    while not marker_file.is_file() and time.monotonic() < deadline:
        time.sleep(0.05)
    assert marker_file.read_text(encoding="utf-8").splitlines() == ["launched"]
