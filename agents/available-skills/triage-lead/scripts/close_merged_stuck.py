#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["requests"]
# ///
"""Bulk-close every "Pull Request"-state ticket whose linked PR is actually
merged (PR_MERGED_STUCK from scan_pull_request_state.py). Each close is
independently re-verified against GitHub at close time via
verify_and_close's verify_pr -- the earlier scan's classification is a
candidate list, not trusted evidence on its own.

Usage: close_merged_stuck.py [TEAM_NAME] [--dry-run]
"""

from __future__ import annotations

import re
import sys

from linear_client import fetch_all_issues, linear_team_id
from verify_and_close import (
    EvidenceError,
    close_issue,
    post_comment,
    resolve_done_state_id,
    resolve_issue,
    verify_pr,
)

ISSUE_FIELDS = """
identifier
title
url
state { name }
attachments { nodes { url } }
"""

PR_URL_RE = re.compile(r"github\.com/([^/]+)/([^/]+)/pull/(\d+)")


def main() -> None:
    args = sys.argv[1:]
    team_name = args[0] if args and not args[0].startswith("--") else "Development"
    dry_run = "--dry-run" in args

    team_id = linear_team_id(team_name)

    def report_progress(count: int) -> None:
        print(f"  fetched {count} issues so far...", file=sys.stderr)

    all_issues = fetch_all_issues(
        team_id, on_page=report_progress, issue_fields=ISSUE_FIELDS
    )
    issues = [i for i in all_issues if i["state"]["name"] == "Pull Request"]
    print(
        f"\n{len(issues)} tickets in 'Pull Request' state to check\n", file=sys.stderr
    )

    closed, skipped, failed = 0, 0, 0

    for issue in issues:
        pr_refs = [
            f"{m.group(1)}/{m.group(2)}#{m.group(3)}"
            for att in issue["attachments"]["nodes"]
            if (m := PR_URL_RE.search(att["url"]))
        ]
        merged_evidence = None
        for ref in pr_refs:
            try:
                merged_evidence = verify_pr(ref)
                break  # first PR that verifies as merged is our evidence
            except EvidenceError:
                continue

        if not merged_evidence:
            skipped += 1
            continue

        print(f"{issue['identifier']}: {merged_evidence}")
        if dry_run:
            closed += 1
            continue

        try:
            internal_id, team_id_for_issue = resolve_issue(issue["identifier"])
            done_state_id = resolve_done_state_id(team_id_for_issue)
            body = (
                f"**Verified evidence:** {merged_evidence}\n\n"
                "Ticket sat in 'Pull Request' state after merge -- closed by "
                "triage-lead's close_merged_stuck.py sweep."
            )
            post_comment(internal_id, body)
            if close_issue(internal_id, done_state_id):
                closed += 1
            else:
                print("  FAIL: issueUpdate did not report success", file=sys.stderr)
                failed += 1
        except EvidenceError as exc:
            print(f"  FAIL: {exc}", file=sys.stderr)
            failed += 1

    print(
        f"\n{'Would close' if dry_run else 'Closed'}: {closed}   skipped (no merged PR): {skipped}   failed: {failed}"
    )


if __name__ == "__main__":
    main()
