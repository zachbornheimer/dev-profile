#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["requests"]
# ///
"""Mechanically flag tickets likely to need EXPAND (the triage-lead move for
turning a vague ticket into a dev-ready one) -- so a reviewer works a short,
scored shortlist instead of reading thousands of tickets by hand.

This is a heuristic filter, not a verdict: it scores against the "good
ticket" criteria in ../SKILL.md (self-contained context, verifiable
done-state, actionable scope) and sorts by how many are missing. A high
score means "worth a human/agent look", not "confirmed bad".

Tickets already owned by an automated lane (security scan, CI failure,
incident, needs-human dispatch) are excluded -- those are triage-lead's
CLOSE/ESCALATE moves, not EXPAND candidates.

Usage: find_expand_candidates.py [TEAM_NAME] [--min-score N] [--limit N]
"""

from __future__ import annotations

import re
import sys

from linear_client import fetch_all_issues, linear_team_id

ISSUE_FIELDS = """
identifier
title
description
priorityLabel
url
project { name }
state { name type }
labels { nodes { name } }
"""

# States meant for grooming before dev, not the bot-firehose lanes.
CANDIDATE_STATE_NAMES = {"Not Ready for Dev", "Unreviewed"}

# Labels that mean "already owned by an automated lane" -- excluded outright.
AUTOMATED_LABELS = {
    "Security",
    "stream:security",
    "stream:automation",
    "stream:incidents",
    "incident",
    "ci-failure",
    "auto-delegated:security",
    "dispatch:failed",
    "pipeline-health",
    "repo:missing",
    "needs-human",
    "[automated]",
    "[sentry]",
}

REQUEST_PHRASING = re.compile(
    r"^(please|can we|can you|we need|request|it would be (nice|great))",
    re.IGNORECASE,
)
AC_MARKERS = re.compile(
    r"acceptance criteria|done-when|done when|\back\b|verify:", re.IGNORECASE
)
REPO_HINT = re.compile(r"`[^`]+`|\brepo[:\s]|\.(ts|js|py|go|rb|php|vue|sql)\b")
IMPERATIVE_VERBS = re.compile(
    r"^(fix|add|remove|update|implement|investigate|migrate|refactor|support|"
    r"allow|enable|disable|prevent|ensure|replace|rename|extract|split|merge|"
    r"document|deprecate|upgrade|downgrade|revert|guard|validate|handle)\b",
    re.IGNORECASE,
)
NON_ATOMIC_TITLE = re.compile(r"\b and \b|/| & ", re.IGNORECASE)


def score_issue(issue: dict) -> tuple[int, list[str]]:
    reasons: list[str] = []
    description = issue["description"] or ""
    title = issue["title"] or ""
    labels = {node["name"] for node in issue["labels"]["nodes"]}
    word_count = len(description.split())

    if word_count < 40:
        reasons.append(f"short description ({word_count} words)")
    if not labels:
        reasons.append("no labels")
    if labels & {"source:support", "liaison:backlog"}:
        reasons.append("support-sourced")
    if not AC_MARKERS.search(description):
        reasons.append("no acceptance-criteria markers")
    if not REPO_HINT.search(description):
        reasons.append("no repo/file/code reference")
    if issue["priorityLabel"] == "No priority":
        reasons.append("no priority set")
    if REQUEST_PHRASING.match(title.strip()):
        reasons.append("request-phrased title")
    if not IMPERATIVE_VERBS.match(title.strip()):
        reasons.append("title has no imperative verb")
    if NON_ATOMIC_TITLE.search(title):
        reasons.append("title joins multiple asks (and/&//)")

    if word_count > 300 and AC_MARKERS.search(description):
        # Long AND has explicit AC/verify markers: almost certainly already
        # well-specified (e.g. a root-cause-and-fix ticket) -- override any
        # other heuristics that happened to fire on it.
        reasons.append("well-specified: long with explicit AC markers (override)")
        return -10, reasons

    return len(reasons), reasons


def main() -> None:
    args = sys.argv[1:]
    team_name = args[0] if args and not args[0].startswith("--") else "Development"
    min_score = 4
    limit = 50
    if "--min-score" in args:
        min_score = int(args[args.index("--min-score") + 1])
    if "--limit" in args:
        limit = int(args[args.index("--limit") + 1])

    team_id = linear_team_id(team_name)

    def report_progress(count: int) -> None:
        print(f"  scanned {count} issues so far...", file=sys.stderr)

    issues = fetch_all_issues(team_id, on_page=report_progress, issue_fields=ISSUE_FIELDS)

    candidates = []
    for issue in issues:
        if issue["state"]["name"] not in CANDIDATE_STATE_NAMES:
            continue
        labels = {node["name"] for node in issue["labels"]["nodes"]}
        if labels & AUTOMATED_LABELS:
            continue
        score, reasons = score_issue(issue)
        if score >= min_score:
            candidates.append((score, issue, reasons))

    candidates.sort(key=lambda c: -c[0])

    print(
        f"{len(candidates)} candidates (score >= {min_score}) "
        f"out of {len(issues)} total issues, showing top {limit}\n"
    )
    for score, issue, reasons in candidates[:limit]:
        print(f"[{score}] {issue['identifier']}  {issue['title']}")
        print(f"      {issue['url']}")
        print(f"      reasons: {', '.join(reasons)}")
        print()


if __name__ == "__main__":
    main()
