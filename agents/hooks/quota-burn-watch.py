#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Stop hook: trigger `quota-burn-review` detached when a weekly quota drops to <= 10% remaining.

Reads the latest row per `(provider, account_key, limit_id)` from `~/.omp/agent/agent.db`'s
`usage_history` table (a ~1 ms local SQLite query). Whenever a weekly / 7-day limit has
`used_fraction >= 0.90` (`<= 10%` left) and the window is weekly (a 5-hour or session window is
never a review trigger), it claims that provider's reset period -- `provider:resets_at`,
deliberately not the limit bucket or the account: one spent weekly window is one question, so a
provider gets one review of that window however many buckets and accounts share it -- in the
hook's state ledger (`~/.local/state/agent-hooks/quota-reviews.jsonl`) under an exclusive file
lock and launches `OMP_REMOTE=auto capability run quota-burn-review` detached in the background.
Every limit bucket and account sharing the period is recorded on the one claim line.

Three guards keep this to one review per period: a period already in the ledger is never
claimed again; the `force` flag is not passed on, so the review's own shared-store claim is
free to refuse a repeat; and `QUOTA_REVIEW_MIN_INTERVAL_SECONDS` spaces launches out so a
machine whose ledger has diverged cannot start a storm. The review itself is the authority:
it claims the period in the shared store before spending any tokens.
"""

from __future__ import annotations

import fcntl
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))

import contextlib

from hook_common import Decision, HookEvent, run_hook
from hook_common.settings import HookSettings

HOOK_NAME = "quota-burn-watch"
THRESHOLD_USED_FRACTION = 0.90
# Launches are spaced out by this much so a ledger that has diverged (or been reset) cannot
# start a review storm. Overridable for tests and for a deliberate fast re-check.
DEFAULT_MIN_INTERVAL_SECONDS = 900


def min_interval_seconds(env: dict[str, str]) -> float:
    raw = env.get("QUOTA_REVIEW_MIN_INTERVAL_SECONDS", "").strip()
    if not raw:
        return float(DEFAULT_MIN_INTERVAL_SECONDS)
    try:
        return max(0.0, float(raw))
    except ValueError:
        return float(DEFAULT_MIN_INTERVAL_SECONDS)


def quota_period_key(provider: str, resets_at: object) -> str:
    """One exhausted weekly window is one question: the provider and the reset instant define it.

    Limit buckets and accounts are left out on purpose. A provider whose weekly window is spent
    gets one review of that window, not one per limit, per account, or per fallback event.
    """
    try:
        reset = int(resets_at or 0)
    except (TypeError, ValueError):
        reset = 0
    return f"{provider}:{reset}"


def agent_db_path(env: dict[str, str]) -> Path:
    override = env.get("OMP_AGENT_DB_PATH", "").strip()
    if override:
        return Path(override).expanduser()
    return Path.home() / ".omp" / "agent" / "agent.db"


def ledger_path(env: dict[str, str]) -> Path:
    """Runtime state, so it lives under the state dir, not in the dotfiles tree.

    It was at `~/.agents/learnings/quota-reviews.jsonl`, where every machine appends its own
    rows to a tracked file: git could never merge the copies, and the pull from the other
    machine collided with the local one. Per-machine claim state has no business in the repo.
    """
    override = env.get("QUOTA_REVIEWS_LEDGER", "").strip()
    if override:
        return Path(override).expanduser()
    return Path.home() / ".local" / "state" / "agent-hooks" / "quota-reviews.jsonl"


def low_weekly_quotas(
    db_file: Path, threshold: float = THRESHOLD_USED_FRACTION
) -> list[dict]:
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
    for (
        provider,
        account_key,
        email,
        limit_id,
        label,
        window_label,
        used_fraction,
        status,
        resets_at,
    ) in rows:
        used = float(used_fraction or 0.0)
        key = quota_period_key(provider, resets_at)
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
                "period_key": key,
            }
        )
    return results


def claim_unreviewed_periods(
    candidates: list[dict], ledger: Path, min_interval: float = 0.0
) -> list[dict]:
    """Claim the reset periods not yet in the ledger, at most one launch per `min_interval` seconds.

    One ledger line per period, listing every account that shares it. A period already recorded is
    never claimed again -- that is what makes the interval between reviews the quota window itself
    rather than the launcher's turn rate.
    """
    if not candidates:
        return []
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with ledger.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        handle.seek(0)
        seen: set[str] = set()
        newest_claim = 0.0
        for line in handle.read().splitlines():
            if not line.strip():
                continue
            try:
                doc = json.loads(line)
            except ValueError:
                continue
            key = doc.get("period_key") or doc.get("ledger_key")
            if isinstance(key, str):
                seen.add(key)
            claimed_at = doc.get("claimed_at")
            if isinstance(claimed_at, str):
                with contextlib.suppress(ValueError):
                    newest_claim = max(
                        newest_claim, datetime.fromisoformat(claimed_at).timestamp()
                    )
        if min_interval > 0 and newest_claim > 0:
            age = datetime.now(timezone.utc).timestamp() - newest_claim
            if age < min_interval:
                return []
        periods: dict[str, dict] = {}
        for item in candidates:
            key = item["period_key"]
            if key in seen:
                continue
            period = periods.setdefault(key, {**item, "accounts": []})
            if item["account_key"] not in period["accounts"]:
                period["accounts"].append(item["account_key"])
        if not periods:
            return []
        now_iso = datetime.now(timezone.utc).isoformat()
        for period in periods.values():
            handle.write(json.dumps({**period, "claimed_at": now_iso}) + "\n")
        handle.flush()
        return list(periods.values())


# A launcher override reaches execve as one argv element, never through a shell. Only a plain
# executable path or name is allowed: anything with a space, quote, or shell metacharacter is a
# configuration error at the call site, so it is refused before the launch (same rule as
# SAFE_TOKEN/plainToken in capability-replicas fleet-offload.ts).
SAFE_LAUNCHER = re.compile(r"^/?[A-Za-z0-9_][A-Za-z0-9._/@:+-]*$")


def resolve_launcher(cmd: str) -> str | None:
    """A launcher override must be an extant executable, resolved by path or by PATH lookup.

    It reaches execve as one argv element with no shell, so there is nothing to inject; the
    check exists so a value cannot point at an arbitrary non-executable or a directory.
    """
    if not cmd or not SAFE_LAUNCHER.match(cmd):
        return None
    if cmd.startswith("/"):
        path = Path(cmd)
        return cmd if path.is_file() and os.access(path, os.X_OK) else None
    return shutil.which(cmd)


def launch_argv(cmd: str) -> list[str]:
    """The argv for one review launch. `force` is deliberately absent: it would bypass the
    review's own per-period claim in the shared store, which is the only guard that survives a
    launcher whose local ledger has diverged."""
    resolved = resolve_launcher(cmd)
    if resolved:
        return [resolved]
    return [
        "capability",
        "run",
        "quota-burn-review",
        "--input",
        json.dumps({"run_optimize_tooling": True}),
    ]


def launch_quota_review(env: dict[str, str]) -> None:
    home = Path.home()
    extra_path = f"{home / 'Developer/Personal/dev-profile/bin'}:{home / '.local/bin'}:{home / '.local/share/aube/bin'}:{home / '.local/share/mise/shims'}:{home / '.bun/bin'}"
    child_env = {
        **env,
        "PATH": f"{extra_path}:{env.get('PATH', '/usr/bin:/bin')}",
        "LEARNER": "1",
        "AGENTMUX_NESTED_RUN": "1",
        "OMP_REMOTE": env.get("OMP_REMOTE") or "auto",
    }
    argv = launch_argv(env.get("QUOTA_REVIEW_LAUNCH_CMD", "").strip())
    state = HookSettings.from_env().state_dir
    state.mkdir(parents=True, exist_ok=True)
    with (state / f"{HOOK_NAME}.err").open("ab") as errors:
        # List argv, no shell: nothing here is re-parsed by a shell, so no argument can inject one.
        subprocess.Popen(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=errors,
            env=child_env,
            shell=False,
            start_new_session=True,
        )


def decide(_event: HookEvent) -> Decision | None:
    env = dict(os.environ)
    if env.get("LEARNER") == "1":
        return None
    candidates = low_weekly_quotas(agent_db_path(env))
    if not candidates:
        return None
    claimed = claim_unreviewed_periods(
        candidates, ledger_path(env), min_interval_seconds(env)
    )
    if not claimed:
        return None
    launch_quota_review(env)
    names = ",".join(
        f"{c['provider']}:{c['limit_id']}({c['remaining_pct']}%left,{len(c['accounts'])}account(s))"
        for c in claimed
    )
    return Decision.no_objection(
        f"launched quota-burn-review for {names}", log_label="launch"
    )


if __name__ == "__main__":
    run_hook(HOOK_NAME, decide)
