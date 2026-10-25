#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Emit a complete, validated inventory of a repository's open pull requests."""

from __future__ import annotations

import datetime as dt
import json
import re
import sys
from collections.abc import Sequence
from typing import Any

from inventory_source import (
    InventoryError,
    Runner,
    api_pages,
    boolean,
    count,
    items,
    json_value,
    mapping,
    run_ghx,
    text,
)

PROGRAM = "inventory-open-prs"
REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
PAGE_SIZE = 100
PR_FIELDS = (
    "number,title,body,url,author,isDraft,baseRefName,headRefName,mergeable,"
    "mergeStateStatus,reviewDecision,additions,deletions,changedFiles,labels,"
    "createdAt,updatedAt"
)


def repository(value: object) -> str:
    name = text(value, "repository identity")
    if not REPOSITORY.fullmatch(name):
        raise InventoryError(f"invalid repository identity: {name!r}")
    return name


def repository_details(repo_hint: str | None, runner: Runner) -> tuple[str, str]:
    if repo_hint is None:
        value = mapping(
            json_value(
                runner(["repo", "view", "--json", "nameWithOwner"]),
                "current repository view",
            ),
            "current repository view",
        )
        repo_hint = repository(value.get("nameWithOwner"))
    requested = repository(repo_hint)
    value = mapping(
        json_value(runner(["api", f"repos/{requested}"]), "repository metadata"),
        "repository metadata",
    )
    canonical = repository(value.get("full_name"))
    if canonical.casefold() != requested.casefold():
        raise InventoryError(
            f"repository mismatch: requested {requested!r}, received {canonical!r}"
        )
    return canonical, text(value.get("default_branch"), "default branch")


def elapsed_days(value: object, now: dt.datetime, context: str) -> int:
    try:
        observed = dt.datetime.fromisoformat(
            text(value, context).replace("Z", "+00:00")
        )
    except ValueError as error:
        raise InventoryError(
            f"malformed {context}: expected ISO-8601 timestamp"
        ) from error
    if observed.tzinfo is None:
        raise InventoryError(f"malformed {context}: timezone is required")
    return max(0, (now - observed).days)


def open_pr_numbers(repo: str, runner: Runner) -> list[int]:
    endpoint = f"repos/{repo}/pulls?state=open&per_page={PAGE_SIZE}"
    records = api_pages(runner, endpoint, "open PR inventory")
    numbers = [
        count(record.get("number"), "open PR number", positive=True)
        for record in records
    ]
    if len(numbers) != len(set(numbers)):
        raise InventoryError("incomplete open PR inventory: duplicate PR number")
    return numbers


def pr_details(repo: str, number: int, runner: Runner) -> dict[str, Any]:
    raw = runner(["pr", "view", str(number), "--repo", repo, "--json", PR_FIELDS])
    value = mapping(json_value(raw, f"PR #{number} metadata"), f"PR #{number} metadata")
    observed_number = count(value.get("number"), f"PR #{number} number", positive=True)
    if observed_number != number:
        raise InventoryError(
            f"PR metadata mismatch: requested #{number}, received #{observed_number}"
        )
    return value


def paths_for(repo: str, number: int, runner: Runner) -> list[str]:
    endpoint = f"repos/{repo}/pulls/{number}/files?per_page={PAGE_SIZE}"
    records = api_pages(runner, endpoint, f"PR #{number} file inventory")
    paths = [
        text(record.get("filename"), f"PR #{number} file path") for record in records
    ]
    if len(paths) != len(set(paths)):
        raise InventoryError(f"incomplete PR #{number} file inventory: duplicate path")
    return paths


def label_names(value: object, number: int) -> list[str]:
    labels = items(value, f"PR #{number} labels")
    return [
        text(
            mapping(label, f"PR #{number} label").get("name"),
            f"PR #{number} label name",
        )
        for label in labels
    ]


def inventory(
    repo_hint: str | None, runner: Runner, now: dt.datetime
) -> dict[str, Any]:
    """Observe all pages before returning one complete public object."""
    repo, default_branch = repository_details(repo_hint, runner)
    initial_cohort = open_pr_numbers(repo, runner)
    prs: list[dict[str, Any]] = []
    for number in initial_cohort:
        record = pr_details(repo, number, runner)
        changed_files = count(record.get("changedFiles"), f"PR #{number} changedFiles")
        paths = paths_for(repo, number, runner)
        if len(paths) != changed_files:
            raise InventoryError(
                f"incomplete PR #{number} file inventory: "
                f"expected {changed_files}, got {len(paths)}"
            )
        author_value = record.get("author")
        author = (
            ""
            if author_value is None
            else text(
                mapping(author_value, f"PR #{number} author").get("login"),
                f"PR #{number} author login",
            )
        )
        prs.append(
            {
                "number": number,
                "title": text(record.get("title"), f"PR #{number} title"),
                "body": text(record.get("body"), f"PR #{number} body"),
                "url": text(record.get("url"), f"PR #{number} URL"),
                "author": author,
                "isDraft": boolean(record.get("isDraft"), f"PR #{number} isDraft"),
                "baseRefName": text(
                    record.get("baseRefName"), f"PR #{number} base branch"
                ),
                "headRefName": text(
                    record.get("headRefName"), f"PR #{number} head branch"
                ),
                "mergeable": text(record.get("mergeable"), f"PR #{number} mergeable"),
                "mergeStateStatus": text(
                    record.get("mergeStateStatus"), f"PR #{number} merge state"
                ),
                "reviewDecision": text(
                    record.get("reviewDecision"),
                    f"PR #{number} review decision",
                    nullable=True,
                ),
                "additions": count(record.get("additions"), f"PR #{number} additions"),
                "deletions": count(record.get("deletions"), f"PR #{number} deletions"),
                "changedFiles": changed_files,
                "labels": label_names(record.get("labels"), number),
                "ageDays": elapsed_days(
                    record.get("createdAt"), now, f"PR #{number} createdAt"
                ),
                "staleDays": elapsed_days(
                    record.get("updatedAt"), now, f"PR #{number} updatedAt"
                ),
                "paths": paths,
                "pathsComplete": True,
                "pathCount": len(paths),
            }
        )
    final_cohort = open_pr_numbers(repo, runner)
    if final_cohort != initial_cohort:
        raise InventoryError(
            "open PR cohort changed during inventory; rerun required: "
            f"before={initial_cohort}, after={final_cohort}"
        )
    return {
        "repo": repo,
        "defaultBranch": default_branch,
        "prs": prs,
        "inventoryComplete": True,
        "openPrCount": len(initial_cohort),
    }


def main(arguments: Sequence[str], runner: Runner = run_ghx) -> int:
    if len(arguments) > 1:
        print(f"usage: {PROGRAM} [owner/repo]", file=sys.stderr)
        return 2
    try:
        output = inventory(
            arguments[0] if arguments else None,
            runner,
            dt.datetime.now(dt.UTC),
        )
    except InventoryError as error:
        print(f"{PROGRAM}: {error}", file=sys.stderr)
        return 1
    json.dump(output, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
