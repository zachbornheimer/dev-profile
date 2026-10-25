#!/usr/bin/env python3
"""Offline ghx fixture for the inventory command's public boundary."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

REPO = "acme/widgets"
SCENARIO = os.environ.get("FAKE_GHX_SCENARIO", "complete")
LOG = os.environ.get("FAKE_GHX_LOG")


def emit(value: object) -> None:
    json.dump(value, sys.stdout)
    sys.stdout.write("\n")


def record(arguments: list[str]) -> None:
    if LOG:
        with Path(LOG).open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(arguments) + "\n")


def metadata(number: int) -> dict[str, object]:
    changed_files = 101 if number == 1 else 1
    return {
        "number": number,
        "title": f"Pull request {number}",
        "body": f"Body {number}",
        "url": f"https://example.invalid/{REPO}/pull/{number}",
        "author": {"login": "octocat"},
        "isDraft": number == 2,
        "baseRefName": "main",
        "headRefName": f"change-{number}",
        "mergeable": "MERGEABLE",
        "mergeStateStatus": "CLEAN",
        "reviewDecision": "APPROVED",
        "additions": number,
        "deletions": number - 1,
        "changedFiles": changed_files,
        "labels": [{"name": "ready"}],
        "createdAt": "2026-08-01T00:00:00Z",
        "updatedAt": "2026-08-30T00:00:00Z",
    }


def pr_pages() -> list[list[dict[str, int]]]:
    if SCENARIO == "shifted-cohort":
        calls = [
            json.loads(line)
            for line in Path(LOG).read_text(encoding="utf-8").splitlines()
        ]
        endpoint = f"repos/{REPO}/pulls?state=open&per_page=100"
        observation = sum(call[-1] == endpoint for call in calls)
        numbers = [*range(1, 101), 102] if observation == 1 else [*range(2, 103)]
        records = [{"number": number} for number in numbers]
        return [records[:100], records[100:]]
    records = [{"number": number} for number in range(1, 102)]
    if SCENARIO == "duplicate-pr":
        records[-1] = {"number": 100}
    return [records[:100], records[100:]]


def file_pages(number: int) -> list[list[dict[str, str]]]:
    total = 101 if number == 1 else 1
    paths = [
        {"filename": f"src/pr-{number}/file-{index:03}.txt"} for index in range(total)
    ]
    if number == 1 and SCENARIO == "incomplete-files":
        paths = paths[:100]
    if number == 1 and SCENARIO == "duplicate-files":
        paths[-1] = paths[0]
    if number == 1 and SCENARIO == "malformed-files":
        return [[{"wrong": "missing filename"}]]
    return [paths[:100], paths[100:]] if len(paths) > 100 else [paths]


def api(arguments: list[str]) -> None:
    endpoint = arguments[-1]
    if endpoint == f"repos/{REPO}":
        emit({"full_name": REPO, "default_branch": "main"})
        return
    if endpoint == f"repos/{REPO}/pulls?state=open&per_page=100":
        if SCENARIO == "command-failure":
            print("fixture provider failure", file=sys.stderr)
            raise SystemExit(17)
        if SCENARIO == "malformed-json":
            sys.stdout.write("not-json\n")
            return
        emit(pr_pages())
        return
    prefix = f"repos/{REPO}/pulls/"
    suffix = "/files?per_page=100"
    if endpoint.startswith(prefix) and endpoint.endswith(suffix):
        number = int(endpoint.removeprefix(prefix).removesuffix(suffix))
        emit(file_pages(number))
        return
    print(f"unexpected api endpoint: {endpoint}", file=sys.stderr)
    raise SystemExit(64)


def main() -> None:
    arguments = sys.argv[1:]
    record(arguments)
    if arguments[:1] == ["api"]:
        api(arguments)
        return
    if arguments[:2] == ["repo", "view"]:
        emit({"nameWithOwner": REPO})
        return
    if arguments[:2] == ["pr", "view"]:
        emit(metadata(int(arguments[2])))
        return
    print(f"unexpected ghx command: {arguments!r}", file=sys.stderr)
    raise SystemExit(64)


if __name__ == "__main__":
    main()
