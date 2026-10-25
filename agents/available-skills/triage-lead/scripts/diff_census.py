#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# ///
"""Before/after report from two census.py snapshots.

Usage: diff_census.py before.json after.json
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path


def counts_by_state(snapshot: dict) -> Counter[str]:
    counts: Counter[str] = Counter()
    for issue in snapshot["issues"]:
        counts[issue["state"]["name"]] += 1
    return counts


def main() -> None:
    if len(sys.argv) != 3:
        print("Usage: diff_census.py before.json after.json", file=sys.stderr)
        raise SystemExit(2)

    before = json.loads(Path(sys.argv[1]).read_text())
    after = json.loads(Path(sys.argv[2]).read_text())

    before_counts = counts_by_state(before)
    after_counts = counts_by_state(after)
    states = sorted(set(before_counts) | set(after_counts))

    print(f"before: {before['capturedAt']}  ->  after: {after['capturedAt']}")
    print()
    print(f"{'state':<24}{'before':>8}{'after':>8}{'delta':>8}")
    total_before = total_after = 0
    for state in states:
        b, a = before_counts[state], after_counts[state]
        total_before += b
        total_after += a
        print(f"{state:<24}{b:>8}{a:>8}{a - b:>8}")

    print()
    print(
        f"TOTAL   before: {total_before}   after: {total_after}   "
        f"delta: {total_after - total_before}"
    )


if __name__ == "__main__":
    main()
