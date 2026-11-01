#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Stop hook: trigger `quota-burn-review` detached whenever a weekly quota drops to <= 10% remaining.

Reads the latest row per `(provider, account_key, limit_id)` from `~/.omp/agent/agent.db`'s
`usage_history` table (a ~1 ms local SQLite query). Whenever a weekly / 7-day limit has
`used_fraction >= 0.90` (`<= 10%` left) and its `provider:account_key:limit_id:resets_at`
key has not yet been recorded in `~/.agents/learnings/quota-reviews.jsonl`, it claims that
key under an exclusive file lock and launches `OMP_REMOTE=auto capability run quota-burn-review`
detached in the background.
"""

from __future__ import annotations

import fcntl
import json
import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))

from hook_common import Decision, HookEvent, run_hook
from hook_common.settings import HookSettings

HOOK_NAME = "quota-burn-watch"
THRESHOLD_USED_FRACTION = 0.90


def agent_db_path(env: dict[str, str]) -> Path:
    override = env.get("OMP_AGENT_DB_PATH", "").strip()
    if override:
        return Path(override).expanduser()
    return Path.home() / ".omp" / "agent" / "agent.db"


def ledger_path(env: dict[str, str]) -> Path:
    override = env.get("QUOTA_REVIEWS_LEDGER", "").strip()
    if override:
        return Path(override).expanduser()
    return Path.home() / ".agents" / "learnings" / "quota-reviews.jsonl"


def low_weekly_quotas(db_file: Path, threshold: float = THRESHOLD_USED_FRACTION) -> list[dict]:
    if not db_file.is_file():
        return []
    query = """
        SELECT provider, account_key, COALESCE(email, ''), limit_id, label,
               COALESCE(window_label, ''), COALESCE(used_fraction, 0.0),
               COALESCE(status, ''), COALESCE(resets_at, 0)
        FROM usage_history
        WHERE id IN (SELECT MAX(id) FROM usage_history GROUP BY provider, account_key, limit_id)
          AND COALESCE(used_fraction, 0.0) >= ?
          AND (
            LOWER(COALESCE(window_label, '')) LIKE '%week%'
            OR LOWER(COALESCE(window_label, '')) LIKE '%7 day%'
            OR LOWER(limit_id) LIKE '%1w%'
            OR LOWER(limit_id) LIKE '%7d%'
            OR LOWER(limit_id) LIKE '%weekly%'
          )
    """
    try:
        conn = sqlite3.connect(f"file:{db_file}?mode=ro", uri=True, timeout=1.0)
        try:
            rows = conn.execute(query, (threshold,)).fetchall()
        finally:
            conn.close()
    except sqlite3.Error:
        return []

    results: list[dict] = []
    for provider, account_key, email, limit_id, label, window_label, used_fraction, status, resets_at in rows:
        used = float(used_fraction or 0.0)
        key = f"{provider}:{account_key}:{limit_id}:{int(resets_at or 0)}"
        results.append(
            {
                "provider": provider,
                "account_key": account_key,
                "email": email,
                "limit_id": limit_id,
                "label": label,
                "window_label": window_label,
                "used_fraction": used,
                "remaining_pct": round(max(0.0, (1.0 - used) * 100.0), 1),
                "status": status,
                "resets_at": int(resets_at or 0),
                "ledger_key": key,
            }
        )
    return results


def claim_unreviewed_quotas(candidates: list[dict], ledger: Path) -> list[dict]:
    if not candidates:
        return []
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with ledger.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        handle.seek(0)
        seen: set[str] = set()
        for line in handle.read().splitlines():
            if not line.strip():
                continue
            try:
                doc = json.loads(line)
                if isinstance(doc.get("ledger_key"), str):
                    seen.add(doc["ledger_key"])
            except ValueError:
                pass
        unreviewed = [item for item in candidates if item["ledger_key"] not in seen]
        if not unreviewed:
            return []
        now_iso = datetime.now(timezone.utc).isoformat()
        for item in unreviewed:
            handle.write(json.dumps({**item, "claimed_at": now_iso}) + "\n")
        handle.flush()
        return unreviewed


def launch_quota_review(env: dict[str, str]) -> None:
    cmd = env.get("QUOTA_REVIEW_LAUNCH_CMD", "").strip()
    home = Path.home()
    extra_path = f"{home / 'Developer/Personal/dev-profile/bin'}:{home / '.local/bin'}:{home / '.local/share/aube/bin'}:{home / '.local/share/mise/shims'}:{home / '.bun/bin'}"
    child_env = {
        **env,
        "PATH": f"{extra_path}:{env.get('PATH', '/usr/bin:/bin')}",
        "LEARNER": "1",
        "AGENTMUX_NESTED_RUN": "1",
        "OMP_REMOTE": env.get("OMP_REMOTE") or "auto",
    }
    argv = (
        [cmd]
        if cmd
        else [
            "capability",
            "run",
            "quota-burn-review",
            "--input",
            json.dumps({"force": True, "run_optimize_tooling": True}),
        ]
    )
    state = HookSettings.from_env().state_dir
    state.mkdir(parents=True, exist_ok=True)
    with (state / f"{HOOK_NAME}.err").open("ab") as errors:
        subprocess.Popen(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=errors,
            env=child_env,
            start_new_session=True,
        )


def decide(_event: HookEvent) -> Decision | None:
    env = dict(os.environ)
    if env.get("LEARNER") == "1":
        return None
    candidates = low_weekly_quotas(agent_db_path(env))
    if not candidates:
        return None
    claimed = claim_unreviewed_quotas(candidates, ledger_path(env))
    if not claimed:
        return None
    launch_quota_review(env)
    names = ",".join(f"{c['provider']}:{c['limit_id']}({c['remaining_pct']}%left)" for c in claimed)
    return Decision.no_objection(f"launched quota-burn-review for {names}", log_label="launch")


if __name__ == "__main__":
    run_hook(HOOK_NAME, decide)
