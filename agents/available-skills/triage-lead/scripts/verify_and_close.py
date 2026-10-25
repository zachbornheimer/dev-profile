#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["requests"]
# ///
"""Close a Linear ticket ONLY if cited GitHub evidence checks out against the
real repo. No evidence, no close — there is no --force. This is the
mechanical enforcement of triage-lead's "never close on the ticket's own
text alone" rule.

Usage:
  verify_and_close.py SAH-1234 --commit owner/repo@sha "evidence note"
  verify_and_close.py SAH-1234 --pr owner/repo#42 "evidence note"

--commit verifies the SHA exists AND is an ancestor of the repo's default
  branch (via GitHub's compare API) -- a commit on an unmerged branch fails.
--pr verifies the PR exists AND its state is MERGED.
"""

from __future__ import annotations

import json
import subprocess
import sys

from linear_client import linear_graphql


class EvidenceError(Exception):
    """Raised when cited GitHub evidence fails verification."""


def gh_api(path: str) -> dict:
    result = subprocess.run(
        ["gh", "api", path], capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        raise EvidenceError(f"gh api {path} failed: {result.stderr.strip()}")
    return json.loads(result.stdout)


def verify_commit(ref: str) -> str:
    owner_repo, sha = ref.split("@", 1)
    owner, repo = owner_repo.split("/", 1)

    try:
        gh_api(f"repos/{owner}/{repo}/commits/{sha}")
    except EvidenceError as exc:
        raise EvidenceError(f"commit {sha} not found in {owner}/{repo}") from exc

    default_branch = gh_api(f"repos/{owner}/{repo}")["default_branch"]
    compare = gh_api(f"repos/{owner}/{repo}/compare/{default_branch}...{sha}")
    if compare["status"] not in ("identical", "behind"):
        raise EvidenceError(
            f"commit {sha} is not on {owner}/{repo}@{default_branch} "
            f"(compare status: {compare['status']})"
        )

    return f"https://github.com/{owner}/{repo}/commit/{sha} (verified present on {default_branch})"


def verify_pr(ref: str) -> str:
    owner_repo, number = ref.split("#", 1)
    owner, repo = owner_repo.split("/", 1)

    result = subprocess.run(
        [
            "gh",
            "pr",
            "view",
            number,
            "--repo",
            f"{owner}/{repo}",
            "--json",
            "state,mergedAt,url",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise EvidenceError(f"PR #{number} not found in {owner}/{repo}")

    pr = json.loads(result.stdout)
    if pr["state"] != "MERGED" or not pr["mergedAt"]:
        raise EvidenceError(
            f"PR #{number} in {owner}/{repo} is not merged (state={pr['state']})"
        )

    return f"{pr['url']} (verified merged at {pr['mergedAt']})"


def resolve_issue(issue_id: str) -> tuple[str, str]:
    query = "query($id: String!) { issue(id: $id) { id team { id } } }"
    data = linear_graphql(query, {"id": issue_id})
    issue = data["data"]["issue"]
    if not issue:
        raise EvidenceError(f"Linear issue {issue_id} not found")
    return issue["id"], issue["team"]["id"]


def resolve_done_state_id(team_id: str) -> str:
    query = """
    query($teamId: ID!) {
      workflowStates(filter: {team: {id: {eq: $teamId}}}) { nodes { id name } }
    }
    """
    data = linear_graphql(query, {"teamId": team_id})
    for state in data["data"]["workflowStates"]["nodes"]:
        if state["name"] == "Done":
            return state["id"]
    raise EvidenceError("no 'Done' workflow state found for this team")


def post_comment(issue_id: str, body: str) -> None:
    mutation = """
    mutation($issueId: String!, $body: String!) {
      commentCreate(input: {issueId: $issueId, body: $body}) { success }
    }
    """
    linear_graphql(mutation, {"issueId": issue_id, "body": body})


def close_issue(internal_id: str, state_id: str) -> bool:
    mutation = """
    mutation($id: String!, $stateId: String!) {
      issueUpdate(id: $id, input: {stateId: $stateId}) { success }
    }
    """
    data = linear_graphql(mutation, {"id": internal_id, "stateId": state_id})
    return bool(data["data"]["issueUpdate"]["success"])


def main() -> None:
    if len(sys.argv) < 4:
        print(
            "Usage: verify_and_close.py ISSUE-ID --commit owner/repo@sha \"note\"\n"
            "       verify_and_close.py ISSUE-ID --pr owner/repo#N \"note\"",
            file=sys.stderr,
        )
        raise SystemExit(2)

    issue_id, flag, ref = sys.argv[1], sys.argv[2], sys.argv[3]
    comment = sys.argv[4] if len(sys.argv) > 4 else ""

    try:
        if flag == "--commit":
            evidence_line = verify_commit(ref)
        elif flag == "--pr":
            evidence_line = verify_pr(ref)
        else:
            print(f"Unknown evidence flag: {flag} (use --commit or --pr)", file=sys.stderr)
            raise SystemExit(2)

        print(f"Verified: {evidence_line}")

        internal_id, team_id = resolve_issue(issue_id)
        done_state_id = resolve_done_state_id(team_id)

        body = f"**Verified evidence:** {evidence_line}"
        if comment:
            body += f"\n\n{comment}"
        post_comment(internal_id, body)

        if close_issue(internal_id, done_state_id):
            print(f"Closed {issue_id} with evidence comment attached.")
        else:
            print("FAIL: Linear issueUpdate did not report success", file=sys.stderr)
            raise SystemExit(5)

    except EvidenceError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(3) from exc


if __name__ == "__main__":
    main()
