#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["requests"]
# ///
"""Diagnose the "Pull Request" workflow state: for every ticket sitting
there, find its linked GitHub PR(s) and check their REAL state via `gh`.
Close-tracking automation appears to react to PR *merge* only -- a PR that
gets closed unmerged because the fix landed via a different commit (a real,
observed pattern: SAH-8033) leaves the ticket stuck indefinitely. This
script classifies every ticket so the pattern's true scope is known, not
guessed from one example.

Usage: scan_pull_request_state.py [TEAM_NAME]
"""

from __future__ import annotations

import json
import re
import subprocess
import sys

from linear_client import fetch_all_issues, linear_team_id

ISSUE_FIELDS = """
identifier
title
url
state { name }
attachments { nodes { url } }
"""

PR_URL_RE = re.compile(r"github\.com/([^/]+)/([^/]+)/pull/(\d+)")


def gh_pr_state(owner: str, repo: str, number: str) -> dict | None:
    result = subprocess.run(
        [
            "gh",
            "api",
            f"repos/{owner}/{repo}/pulls/{number}",
            "--jq",
            "{state: .state, merged: .merged, title: .title, updated_at: .updated_at}",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    return json.loads(result.stdout)


def classify(pr_states: list[dict]) -> str:
    if not pr_states:
        return "NO_PR_LINKED"
    if any(p["merged"] for p in pr_states):
        return "PR_MERGED_STUCK"
    if any(p["state"] == "open" for p in pr_states):
        return "PR_OPEN_LEGIT"
    return "PR_CLOSED_UNMERGED"


def main() -> None:
    team_name = sys.argv[1] if len(sys.argv) > 1 else "Development"
    team_id = linear_team_id(team_name)

    def report_progress(count: int) -> None:
        print(f"  fetched {count} issues so far...", file=sys.stderr)

    all_issues = fetch_all_issues(team_id, on_page=report_progress, issue_fields=ISSUE_FIELDS)
    issues = [i for i in all_issues if i["state"]["name"] == "Pull Request"]
    print(f"\n{len(issues)} tickets in 'Pull Request' state\n", file=sys.stderr)

    results: dict[str, list[dict]] = {
        "NO_PR_LINKED": [],
        "PR_OPEN_LEGIT": [],
        "PR_MERGED_STUCK": [],
        "PR_CLOSED_UNMERGED": [],
    }

    for n, issue in enumerate(issues, 1):
        pr_refs = []
        for att in issue["attachments"]["nodes"]:
            match = PR_URL_RE.search(att["url"])
            if match:
                pr_refs.append(match.groups())

        pr_states = []
        for owner, repo, number in pr_refs:
            state = gh_pr_state(owner, repo, number)
            if state:
                pr_states.append(state)

        category = classify(pr_states)
        results[category].append(
            {"identifier": issue["identifier"], "title": issue["title"], "url": issue["url"], "prs": pr_states}
        )
        if n % 50 == 0:
            print(f"  checked {n}/{len(issues)}...", file=sys.stderr)

    print("== Summary ==")
    for category, items in results.items():
        print(f"{category}: {len(items)}")

    print("\n== PR_MERGED_STUCK (fix merged, ticket never closed) ==")
    for item in results["PR_MERGED_STUCK"]:
        print(f"{item['identifier']}  {item['title']}\n  {item['url']}")

    print("\n== PR_CLOSED_UNMERGED (needs a look -- may be SAH-8033's pattern) ==")
    for item in results["PR_CLOSED_UNMERGED"]:
        print(f"{item['identifier']}  {item['title']}\n  {item['url']}")

    print("\n== NO_PR_LINKED (stuck in Pull Request state with no PR attached at all) ==")
    for item in results["NO_PR_LINKED"][:20]:
        print(f"{item['identifier']}  {item['title']}\n  {item['url']}")
    if len(results["NO_PR_LINKED"]) > 20:
        print(f"  ... and {len(results['NO_PR_LINKED']) - 20} more")


if __name__ == "__main__":
    main()
