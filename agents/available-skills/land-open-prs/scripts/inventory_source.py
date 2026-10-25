"""Validated access to the inventory's external command and JSON values."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable, Sequence
from typing import Any

PAGE_SIZE = 100
Runner = Callable[[Sequence[str]], str]


class InventoryError(Exception):
    """The provider did not prove a complete, trustworthy inventory."""


def run_ghx(arguments: Sequence[str]) -> str:
    """Run the sole provider/process boundary."""
    try:
        completed = subprocess.run(
            ["ghx", *arguments], check=False, text=True, capture_output=True
        )
    except FileNotFoundError as error:
        raise InventoryError(
            "ghx is required for GitHub operations (not gh)"
        ) from error
    except OSError as error:
        raise InventoryError(f"could not start ghx: {error}") from error
    if completed.returncode:
        detail = completed.stderr.strip() or completed.stdout.strip() or "no output"
        raise InventoryError(f"ghx command failed ({' '.join(arguments)}): {detail}")
    return completed.stdout


def json_value(raw: str, operation: str) -> Any:
    try:
        return json.loads(raw)
    except json.JSONDecodeError as error:
        raise InventoryError(f"malformed JSON from {operation}: {error.msg}") from error


def mapping(value: object, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise InventoryError(f"malformed {context}: expected object")
    return value


def items(value: object, context: str) -> list[Any]:
    if not isinstance(value, list):
        raise InventoryError(f"malformed {context}: expected list")
    return value


def text(value: object, context: str, *, nullable: bool = False) -> str:
    if nullable and value is None:
        return ""
    if not isinstance(value, str):
        raise InventoryError(f"malformed {context}: expected text")
    return value


def count(value: object, context: str, *, positive: bool = False) -> int:
    minimum = 1 if positive else 0
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        kind = "positive" if positive else "non-negative"
        raise InventoryError(f"malformed {context}: expected {kind} integer")
    return value


def boolean(value: object, context: str) -> bool:
    if not isinstance(value, bool):
        raise InventoryError(f"malformed {context}: expected boolean")
    return value


def api_pages(runner: Runner, endpoint: str, operation: str) -> list[dict[str, Any]]:
    raw = runner(["api", "--paginate", "--slurp", endpoint])
    pages = items(json_value(raw, operation), f"{operation} pages")
    if not pages:
        raise InventoryError(f"incomplete {operation}: no pages returned")
    records: list[dict[str, Any]] = []
    for index, page in enumerate(pages):
        page_items = items(page, f"{operation} page {index + 1}")
        if index < len(pages) - 1 and len(page_items) != PAGE_SIZE:
            raise InventoryError(
                f"incomplete {operation} page {index + 1}: "
                f"expected {PAGE_SIZE} records before another page, got {len(page_items)}"
            )
        if index and not page_items:
            raise InventoryError(f"malformed {operation} page {index + 1}: empty page")
        records.extend(
            mapping(item, f"{operation} page {index + 1} item {item_index + 1}")
            for item_index, item in enumerate(page_items)
        )
    return records
