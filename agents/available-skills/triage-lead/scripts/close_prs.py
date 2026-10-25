#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# ///
"""Close a reviewed list of pull requests with one explanatory comment each.

Usage:
  close_prs.py OWNER/REPO NUMBERS.json "comment text" LOG.jsonl

NUMBERS.json is a JSON list of PR numbers produced and reviewed beforehand
(never computed here). Each close is logged as one JSON line so the run is
auditable and resumable: PRs already present in LOG.jsonl are skipped.
Branches are left intact; closing only.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


# GitHub's secondary rate limit rejects comments "submitted too quickly";
# pacing every close keeps a long run under it.
PACE_SECONDS = 3.0
RETRIES = 3


def already_done(log: Path) -> set[int]:
    """PR numbers already closed successfully; failures are retried."""
    if not log.exists():
        return set()
    done = set()
    for line in log.read_text().splitlines():
        if line.strip():
            entry = json.loads(line)
            if entry.get("closed"):
                done.add(entry["number"])
    return done


def close_one(repo: str, number: int, comment: str) -> tuple[bool, str]:
    detail = ""
    for attempt in range(RETRIES):
        if attempt:
            time.sleep(PACE_SECONDS * (attempt + 1) * 5)
        result = subprocess.run(
            ["gh", "pr", "close", str(number), "--repo", repo, "--comment", comment],
            capture_output=True,
            text=True,
            check=False,
        )
        detail = (result.stderr or result.stdout).strip()
        if result.returncode == 0 or "already closed" in detail:
            return True, ""
    return False, detail


def main() -> None:
    if len(sys.argv) != 5:
        print(__doc__, file=sys.stderr)
        raise SystemExit(2)
    repo, numbers_path, comment, log_path = sys.argv[1:]
    numbers = json.loads(Path(numbers_path).read_text())
    log = Path(log_path)
    done = already_done(log)

    closed = failed = 0
    with log.open("a") as out:
        for number in numbers:
            if number in done:
                continue
            ok, detail = close_one(repo, number, comment)
            out.write(json.dumps({
                "ts": datetime.now(timezone.utc).isoformat(),
                "repo": repo,
                "number": number,
                "closed": ok,
                "detail": "" if ok else detail,
            }) + "\n")
            out.flush()
            closed += ok
            failed += not ok
            time.sleep(PACE_SECONDS)
    print(f"{repo}: closed {closed}, failed {failed}, skipped {len(done)} already logged")
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
