#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["requests"]
# ///
"""Deterministic snapshot of Linear issues for a team: exact counts per
workflow state and per label, via the Linear GraphQL API directly (no MCP,
no agent judgment, no sampling). Run before and after a triage pass, then
feed both snapshots to diff_census.py for a before/after report.

Usage: census.py [TEAM_NAME] [OUTPUT_JSON_PATH]
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from linear_client import fetch_all_issues, linear_team_id


def main() -> None:
    team_name = sys.argv[1] if len(sys.argv) > 1 else "Development"
    out_path = (
        sys.argv[2]
        if len(sys.argv) > 2
        else f"census-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}.json"
    )

    team_id = linear_team_id(team_name)

    def report_progress(count: int) -> None:
        print(f"  fetched {count} issues so far...", file=sys.stderr)

    issues = fetch_all_issues(team_id, on_page=report_progress)

    snapshot = {
        "team": team_name,
        "capturedAt": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "issues": issues,
    }
    Path(out_path).write_text(json.dumps(snapshot, indent=2))
    print(f"Snapshot written: {out_path}", file=sys.stderr)
    print(file=sys.stderr)

    by_state: Counter[tuple[str, str]] = Counter()
    for issue in issues:
        state = issue["state"]
        by_state[(state["name"], state["type"])] += 1

    print("== By state ==")
    print(f"{'state':<24}{'type':<12}{'count':>6}")
    for (name, type_), count in sorted(by_state.items(), key=lambda kv: -kv[1]):
        print(f"{name:<24}{type_:<12}{count:>6}")
    print(f"{'TOTAL':<24}{'':<12}{len(issues):>6}")

    label_counts: Counter[str] = Counter()
    for issue in issues:
        for label in issue["labels"]["nodes"]:
            label_counts[label["name"]] += 1

    print()
    print("== Top labels ==")
    for label, count in label_counts.most_common():
        print(f"{label:<28}{count:>6}")


if __name__ == "__main__":
    main()
