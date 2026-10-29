#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["requests"]
# ///
"""Find and (optionally) close moot PRs: any open PR -- draft or not, any
repo, any author, any title -- that would change ZERO files if merged into
the CURRENT default branch right now. This is git-mechanical, not a pattern
match for one incident type: it catches a PR whose target file was deleted
or already changed to make the PR's diff a no-op, a PR whose fix already
landed via a different commit (this org's own SAH-8033 is exactly this:
closed by hand with "Already on main... Closing as landed"), and a PR that
never had a real diff to begin with. It does NOT try to detect "duplicate"
or "superseded-by-a-similar-but-not-identical PR" -- that needs judgment
about which is the real survivor and is out of scope here.

A PR only qualifies if it is also older than MOOT_MIN_AGE_HOURS (default
24h) -- short-lived zero-diff PRs are a known, legitimate pattern (empty
commits to retrigger CI after a transient failure, branch-freshness bumps,
canary/health-check probes) and are usually closed or merged within
minutes to hours on their own. Only a zero-diff PR that's been sitting
around for a day+ is a real cleanup candidate.

Usage:
  find_moot_prs.py owner/repo                     # one repo, list only
  find_moot_prs.py owner                          # every repo in the org, list only
  find_moot_prs.py owner/repo --execute            # actually close them
  find_moot_prs.py owner/repo --execute --limit 20
  find_moot_prs.py owner/repo --min-age-hours 48
  find_moot_prs.py owner --execute --link-linear   # also comment on each PR's
                                                     # Linear ticket (never
                                                     # auto-closes the ticket --
                                                     # a moot PR doesn't prove
                                                     # the ticket's goal was
                                                     # met, only that this PR
                                                     # won't do it)
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import UTC, datetime

DEFAULT_MIN_AGE_HOURS = 24
TICKET_ID_RE = re.compile(r"\bSAH-\d+\b")


def gh_api_paginated(path: str) -> list[dict]:
    result = subprocess.run(
        ["gh", "api", path, "--paginate"], capture_output=True, text=True, check=True
    )
    text = result.stdout.strip()
    if not text:
        return []
    pages: list[dict] = []
    decoder = json.JSONDecoder()
    idx = 0
    while idx < len(text):
        obj, end = decoder.raw_decode(text, idx)
        pages.extend(obj)
        idx = end
        while idx < len(text) and text[idx].isspace():
            idx += 1
    return pages


def gh_api(path: str) -> dict:
    result = subprocess.run(
        ["gh", "api", path], capture_output=True, text=True, check=True
    )
    return json.loads(result.stdout)


def list_org_repos(org: str) -> list[str]:
    repos = gh_api_paginated(f"orgs/{org}/repos?per_page=100")
    return [r["full_name"] for r in repos if not r.get("archived")]


def default_branch(repo: str) -> str:
    return gh_api(f"repos/{repo}")["default_branch"]


def fetch_open_prs(repo: str) -> list[dict]:
    return gh_api_paginated(f"repos/{repo}/pulls?state=open&per_page=100")


def age_hours(created_at: str) -> float:
    created = datetime.fromisoformat(created_at)
    return (datetime.now(UTC) - created).total_seconds() / 3600


def would_change_nothing(repo: str, base: str, head_sha: str) -> bool:
    """True if merging head_sha into base right now would touch zero files."""
    compare = gh_api(f"repos/{repo}/compare/{base}...{head_sha}")
    return len(compare.get("files") or []) == 0


def close_pr(repo: str, number: int) -> None:
    note = (
        "Closed by triage-lead's find_moot_prs.py: merging this PR into the "
        "current default branch would change zero files -- its diff is "
        "already reflected on main or its premise no longer applies."
    )
    subprocess.run(
        ["gh", "pr", "close", str(number), "--repo", repo, "--comment", note],
        check=True,
    )


def find_ticket_id(pr: dict) -> str | None:
    for text in (pr.get("title") or "", pr.get("body") or ""):
        match = TICKET_ID_RE.search(text)
        if match:
            return match.group(0)
    return None


def comment_on_ticket(ticket_id: str, repo: str, number: int) -> str:
    """Post evidence to the ticket linked from a moot PR. Never closes it --
    a moot PR proves this PR won't deliver the ticket's goal, not that the
    goal was already met some other way. That call needs a real look."""
    from linear_client import linear_graphql

    issue_query = "query($id: String!) { issue(id: $id) { id state { name type } } }"
    data = linear_graphql(issue_query, {"id": ticket_id})
    issue = data["data"]["issue"]
    if not issue:
        return f"skip: {ticket_id} not found in Linear"
    if issue["state"]["type"] in ("completed", "canceled", "duplicate"):
        return f"skip: {ticket_id} already {issue['state']['name']}"

    body = (
        f"**triage-lead find_moot_prs.py:** linked PR {repo}#{number} is moot "
        "-- merging it into the current default branch would change zero "
        "files. This does NOT confirm the ticket's goal was met elsewhere; "
        "it only means this PR won't deliver it. Needs a human/agent look: "
        "either the fix landed via a different commit (safe to close with "
        "that evidence) or the underlying work is still undone (needs a "
        "fresh PR)."
    )
    mutation = (
        "mutation($issueId: String!, $body: String!) "
        "{ commentCreate(input: {issueId: $issueId, body: $body}) { success } }"
    )
    linear_graphql(mutation, {"issueId": issue["id"], "body": body})
    return f"commented: {ticket_id} ({issue['state']['name']})"


def main() -> None:
    args = sys.argv[1:]
    if not args:
        print(__doc__, file=sys.stderr)
        raise SystemExit(2)

    target = args[0]
    execute = "--execute" in args
    link_linear = "--link-linear" in args
    limit = int(args[args.index("--limit") + 1]) if "--limit" in args else None
    min_age_hours = (
        float(args[args.index("--min-age-hours") + 1])
        if "--min-age-hours" in args
        else DEFAULT_MIN_AGE_HOURS
    )

    repos = [target] if "/" in target else list_org_repos(target)
    print(
        f"Scanning {len(repos)} repo(s), min age {min_age_hours}h: "
        f"{', '.join(repos[:5])}{'...' if len(repos) > 5 else ''}\n",
        file=sys.stderr,
    )

    all_moot: list[tuple[str, dict]] = []
    for repo in repos:
        base = default_branch(repo)
        prs = fetch_open_prs(repo)
        repo_moot = 0
        for n, pr in enumerate(prs, 1):
            if age_hours(pr["created_at"]) < min_age_hours:
                continue
            if would_change_nothing(repo, base, pr["head"]["sha"]):
                all_moot.append((repo, pr))
                repo_moot += 1
            if n % 100 == 0:
                print(
                    f"  {repo}: checked {n}/{len(prs)}, {repo_moot} moot so far",
                    file=sys.stderr,
                )
        print(
            f"  {repo}: {len(prs)} open, {repo_moot} moot (age >= {min_age_hours}h)",
            file=sys.stderr,
        )

    if limit:
        all_moot = all_moot[:limit]

    print(
        f"\n{len(all_moot)} moot PRs found (zero-diff against current default branch, age >= {min_age_hours}h)\n"
    )
    for repo, pr in all_moot:
        print(
            f"{repo}#{pr['number']}  {pr['title']}  (draft={pr['draft']}, created={pr['created_at']})"
        )

    if not execute:
        print("\nDry run -- no PRs closed. Re-run with --execute to close these.")
        return

    print(f"\nClosing {len(all_moot)} PRs...")
    closed = 0
    for repo, pr in all_moot:
        try:
            close_pr(repo, pr["number"])
            closed += 1
        except subprocess.CalledProcessError as exc:
            print(f"  FAIL closing {repo}#{pr['number']}: {exc}", file=sys.stderr)
            continue
        if link_linear:
            ticket_id = find_ticket_id(pr)
            if not ticket_id:
                print(
                    f"  no SAH-#### found in {repo}#{pr['number']}, skipping Linear link"
                )
                continue
            try:
                print(f"  {comment_on_ticket(ticket_id, repo, pr['number'])}")
            except (
                KeyError,
                ValueError,
                subprocess.CalledProcessError,
                SystemExit,
            ) as linear_error:
                print(
                    f"  FAIL commenting on {ticket_id}: {linear_error}", file=sys.stderr
                )
    print(f"Closed {closed}/{len(all_moot)}")


if __name__ == "__main__":
    main()
