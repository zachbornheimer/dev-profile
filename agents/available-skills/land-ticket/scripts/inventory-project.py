#!/usr/bin/env python3
"""Emit [{id, workspace, mcp}] for Linear identifiers. No network."""

from __future__ import annotations

import json
import sys
from typing import TextIO

from route import InvalidIdentifierError, UnknownPrefixError, route_for

JSON_ID = "id"
JSON_WORKSPACE = "workspace"
JSON_MCP = "mcp"
EMPTY_INPUT_MESSAGE = "no Linear identifiers on argv or stdin"


def collect_identifiers(argv: list[str], stdin: TextIO) -> list[str]:
    if argv:
        return list(argv)
    return stdin.read().split()


def inventory(identifiers: list[str]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for identifier in identifiers:
        routed = route_for(identifier)
        rows.append(
            {
                JSON_ID: identifier,
                JSON_WORKSPACE: routed.workspace,
                JSON_MCP: routed.mcp,
            }
        )
    return rows


def execute_inventory(rows: list[dict[str, str]], stdout: TextIO) -> None:
    json.dump(rows, stdout)
    stdout.write("\n")


def main(
    argv: list[str] | None = None,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    args = sys.argv[1:] if argv is None else argv
    source = sys.stdin if stdin is None else stdin
    out = sys.stdout if stdout is None else stdout
    err = sys.stderr if stderr is None else stderr
    identifiers = collect_identifiers(args, source)
    if not identifiers:
        print(EMPTY_INPUT_MESSAGE, file=err)
        return 1
    try:
        rows = inventory(identifiers)
    except (InvalidIdentifierError, UnknownPrefixError) as error:
        print(str(error), file=err)
        return 1
    execute_inventory(rows, out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
