"""Shared Linear GraphQL client: key retrieval + paginated queries."""

from __future__ import annotations

import os
import subprocess
import sys

import requests

LINEAR_GRAPHQL_URL = "https://api.linear.app/graphql"
OP_KEY_REF = "op://SAH/SAH Linear Claude Code Key/credential"


def linear_api_key() -> str:
    key = os.environ.get("LINEAR_API_KEY")
    if key:
        return key
    try:
        result = subprocess.run(
            ["op", "read", OP_KEY_REF],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        print(
            "No LINEAR_API_KEY set and 'op read' failed. "
            "Run 'op signin' or export LINEAR_API_KEY.",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc


def linear_graphql(query: str, variables: dict) -> dict:
    resp = requests.post(
        LINEAR_GRAPHQL_URL,
        json={"query": query, "variables": variables},
        headers={
            "Authorization": linear_api_key(),
            "Content-Type": "application/json",
        },
        timeout=30,
    )
    data = resp.json()
    if data.get("errors"):
        print(f"Linear API error: {data['errors']}", file=sys.stderr)
        raise SystemExit(1)
    return data


def linear_team_id(name: str) -> str:
    query = """
    query($name: String!) {
      teams(filter: {name: {eq: $name}}) { nodes { id name } }
    }
    """
    data = linear_graphql(query, {"name": name})
    nodes = data["data"]["teams"]["nodes"]
    if not nodes:
        print(f"Team '{name}' not found.", file=sys.stderr)
        raise SystemExit(1)
    return nodes[0]["id"]


DEFAULT_ISSUE_FIELDS = "identifier state { name type } labels { nodes { name } }"


def fetch_all_issues(
    team_id: str,
    on_page: "callable | None" = None,
    issue_fields: str = DEFAULT_ISSUE_FIELDS,
) -> list[dict]:
    """Paginate every issue for a team, requesting the given GraphQL field
    selection. Pass a richer `issue_fields` string to pull title/description/
    etc for scripts that need more than the state+label census."""
    query = f"""
    query($teamId: ID!, $after: String) {{
      issues(filter: {{team: {{id: {{eq: $teamId}}}}}}, first: 100, after: $after) {{
        nodes {{ {issue_fields} }}
        pageInfo {{ hasNextPage endCursor }}
      }}
    }}
    """
    issues: list[dict] = []
    cursor = None
    while True:
        data = linear_graphql(query, {"teamId": team_id, "after": cursor})
        page = data["data"]["issues"]
        issues.extend(page["nodes"])
        if on_page:
            on_page(len(issues))
        if not page["pageInfo"]["hasNextPage"]:
            break
        cursor = page["pageInfo"]["endCursor"]
    return issues
