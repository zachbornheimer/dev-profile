#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# ///
"""Render strict status-report JSON as compact Cargo/Brew-style terminal output.

Preferred agent usage:
    uv run scripts/render.py --json '{"version":2,...}'

The model supplies facts and check states. This program validates them, derives
issue/report state, and owns colors, symbols, wrapping, sorting, and layout.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, TextIO

RESET: Final = "\x1b[0m"
BOLD: Final = "\x1b[1m"
DIM: Final = "\x1b[2m"
RED: Final = "\x1b[31m"
GREEN: Final = "\x1b[32m"
BLUE: Final = "\x1b[34m"

STATUSES: Final = {"done", "in_progress", "not_started"}
STATUS_ORDER: Final = {"in_progress": 0, "not_started": 1, "done": 2}


class ReportError(ValueError):
    """Raised when report JSON is syntactically or semantically invalid."""


@dataclass(frozen=True, slots=True)
class Check:
    """One evidence-backed progress checkpoint."""

    name: str
    status: str
    detail: str
    evidence: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Issue:
    """One ticket-sized work item."""

    issue_id: str
    summary: str
    checks: tuple[Check, ...]


@dataclass(frozen=True, slots=True)
class Report:
    """Validated status-report input."""

    version: int
    effort: str
    summary: str
    issues: tuple[Issue, ...]


@dataclass(frozen=True, slots=True)
class Palette:
    """ANSI palette that can be disabled without changing semantics."""

    enabled: bool

    def wrap(self, code: str, text: str) -> str:
        """Wrap text in ANSI styling when enabled."""
        return f"{code}{text}{RESET}" if self.enabled else text


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    args = parse_args(argv)
    try:
        report = parse_report(read_input(args))
    except (OSError, ReportError) as exc:
        print(f"status-report: {exc}", file=sys.stderr)
        return 1

    if args.validate_only:
        print("valid")
        return 0

    render(
        sys.stdout,
        report,
        Palette(enabled=resolve_color(args.color, sys.stdout)),
        terminal_width(),
    )
    return 0


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    """Parse CLI options; inline JSON is the preferred agent interface."""
    parser = argparse.ArgumentParser(
        prog="status-report", description="Render status-report JSON."
    )
    parser.add_argument("--json", dest="json_text", help="report JSON as one argument")
    parser.add_argument(
        "--stdin", action="store_true", help="read report JSON from stdin"
    )
    parser.add_argument(
        "--color",
        choices=("auto", "always", "never"),
        default="auto",
        help="ANSI color mode (default: auto)",
    )
    parser.add_argument(
        "--validate-only", action="store_true", help="validate without rendering"
    )
    parser.add_argument(
        "path", nargs="?", help="optional JSON file path for manual use"
    )

    args = parser.parse_args(argv)
    input_count = (
        int(args.json_text is not None) + int(args.stdin) + int(args.path is not None)
    )
    if input_count != 1:
        parser.error("provide exactly one input: --json, --stdin, or a file path")
    return args


def read_input(args: argparse.Namespace) -> str:
    """Read input without requiring a temporary report file."""
    if args.json_text is not None:
        return args.json_text
    if args.stdin:
        return sys.stdin.read()
    return Path(args.path).read_text(encoding="utf-8")


def parse_report(raw: str) -> Report:
    """Decode strict JSON, reject unknown fields, and validate semantic values."""
    try:
        data = json.loads(
            raw, object_pairs_hook=_unique_object, parse_constant=_reject_json_constant
        )
    except (json.JSONDecodeError, ReportError) as exc:
        raise ReportError(f"decode JSON: {exc}") from exc

    obj = _expect_object(data, "report")
    _expect_keys(obj, "report", required={"version", "effort", "summary", "issues"})

    version = _expect_int(obj["version"], "version")
    if version != 2:
        raise ReportError("version must be 2")

    effort = _expect_string(obj["effort"], "effort", max_length=120)
    summary = _expect_string(obj["summary"], "summary", max_length=240)
    issue_values = _expect_list(obj["issues"], "issues", min_items=1)

    issues: list[Issue] = []
    seen_ids: set[str] = set()
    for index, value in enumerate(issue_values):
        prefix = f"issues[{index}]"
        issue_obj = _expect_object(value, prefix)
        _expect_keys(issue_obj, prefix, required={"issueId", "summary", "checks"})

        issue_id = _expect_string(
            issue_obj["issueId"], f"{prefix}.issueId", max_length=40
        )
        if issue_id in seen_ids:
            raise ReportError(f'{prefix}.issueId "{issue_id}" is duplicated')
        seen_ids.add(issue_id)

        issue_summary = _expect_string(
            issue_obj["summary"], f"{prefix}.summary", max_length=280
        )
        check_values = _expect_list(
            issue_obj["checks"], f"{prefix}.checks", min_items=1
        )

        checks: list[Check] = []
        seen_checks: set[str] = set()
        for check_index, check_value in enumerate(check_values):
            check_prefix = f"{prefix}.checks[{check_index}]"
            check_obj = _expect_object(check_value, check_prefix)
            _expect_keys(
                check_obj,
                check_prefix,
                required={"name", "status", "detail", "evidence"},
            )

            name = _expect_string(
                check_obj["name"], f"{check_prefix}.name", max_length=80
            )
            if name in seen_checks:
                raise ReportError(f'{check_prefix}.name "{name}" is duplicated')
            seen_checks.add(name)

            status = _expect_string(check_obj["status"], f"{check_prefix}.status")
            if status not in STATUSES:
                raise ReportError(
                    f'{check_prefix}.status "{status}" is invalid; '
                    "use done, in_progress, or not_started"
                )

            detail = _expect_string(
                check_obj["detail"], f"{check_prefix}.detail", max_length=400
            )
            evidence_values = _expect_list(
                check_obj["evidence"], f"{check_prefix}.evidence", min_items=1
            )
            evidence = tuple(
                _expect_string(
                    item, f"{check_prefix}.evidence[{evidence_index}]", max_length=400
                )
                for evidence_index, item in enumerate(evidence_values)
            )
            checks.append(
                Check(name=name, status=status, detail=detail, evidence=evidence)
            )

        issues.append(
            Issue(issue_id=issue_id, summary=issue_summary, checks=tuple(checks))
        )

    return Report(version=version, effort=effort, summary=summary, issues=tuple(issues))


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """Reject duplicate JSON keys instead of silently taking the last value."""
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ReportError(f'duplicate object key "{key}"')
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    """Reject non-standard NaN/Infinity JSON extensions."""
    raise ReportError(f"invalid JSON constant {value}")


def _expect_object(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ReportError(f"{path} must be an object")
    return value


def _expect_keys(
    value: dict[str, Any],
    path: str,
    *,
    required: set[str],
    optional: set[str] | None = None,
) -> None:
    optional = optional or set()
    missing = required - value.keys()
    if missing:
        raise ReportError(
            f"{path} missing required field(s): {', '.join(sorted(missing))}"
        )
    unknown = value.keys() - required - optional
    if unknown:
        raise ReportError(f"{path} has unknown field(s): {', '.join(sorted(unknown))}")


def _expect_string(value: Any, path: str, *, max_length: int | None = None) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ReportError(f"{path} must be a non-empty string")
    if max_length is not None and len(value) > max_length:
        raise ReportError(f"{path} must be <= {max_length} characters")
    return value.strip()


def _expect_int(value: Any, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ReportError(f"{path} must be an integer")
    return value


def _expect_list(value: Any, path: str, *, min_items: int = 0) -> list[Any]:
    if not isinstance(value, list):
        raise ReportError(f"{path} must be an array")
    if len(value) < min_items:
        raise ReportError(f"{path} requires at least {min_items} item(s)")
    return value


def resolve_color(mode: str, stdout: TextIO) -> bool:
    """Resolve color according to explicit mode, NO_COLOR, FORCE_COLOR, and TTY state."""
    if mode == "always":
        return True
    if mode == "never":
        return False
    if os.getenv("NO_COLOR"):
        return False
    if os.getenv("FORCE_COLOR"):
        return True
    return stdout.isatty()


def terminal_width() -> int:
    """Return a bounded width so output stays readable in wide terminals."""
    try:
        configured = int(os.getenv("COLUMNS", ""))
    except ValueError:
        configured = 0
    if configured >= 72:
        return min(configured, 180)
    return min(max(shutil.get_terminal_size(fallback=(120, 24)).columns, 72), 180)


def derive_issue_status(issue: Issue) -> str:
    """Derive issue state from its checks so model and rendered state cannot disagree."""
    statuses = {check.status for check in issue.checks}
    if statuses == {"done"}:
        return "done"
    if statuses == {"not_started"}:
        return "not_started"
    return "in_progress"


def derive_report_status(report: Report) -> str:
    """Derive overall status from issue states."""
    statuses = {derive_issue_status(issue) for issue in report.issues}
    if statuses == {"done"}:
        return "done"
    if statuses == {"not_started"}:
        return "not_started"
    return "in_progress"


def status_visual(status: str) -> tuple[str, str, str]:
    """Map one of the only three semantic states to label, color, and marker."""
    return {
        "done": ("DONE", GREEN, "✔"),
        "in_progress": ("IN PROGRESS", BLUE, "●"),
        "not_started": ("NOT STARTED", RED, "✘"),
    }[status]


def render(output: TextIO, report: Report, palette: Palette, width: int) -> None:
    """Render headline, compact issue table, then status-bearing per-ticket checks."""
    report_status = derive_report_status(report)
    status_label, status_color, _ = status_visual(report_status)
    counts = count_issue_statuses(report)

    print(file=output)
    print(
        f"{palette.wrap(BOLD, 'STATUS')}  {palette.wrap(BOLD, report.effort)}  "
        f"{palette.wrap(BOLD + status_color, status_label)}",
        file=output,
    )
    print(report.summary, file=output)
    print(
        "  "
        + "  ".join(
            (
                palette.wrap(GREEN, f"{counts['done']} done"),
                palette.wrap(BLUE, f"{counts['in_progress']} in progress"),
                palette.wrap(RED, f"{counts['not_started']} not started"),
            )
        ),
        file=output,
    )
    print(file=output)

    render_table(output, report.issues, palette, width)

    for issue in sorted_issues(report.issues):
        issue_status = derive_issue_status(issue)
        issue_label, issue_color, _ = status_visual(issue_status)
        heading = (
            f"{palette.wrap(BOLD, issue.issue_id)}  "
            f"{palette.wrap(BOLD + issue_color, issue_label)}"
        )
        print(f"\n{heading}", file=output)
        print(issue.summary, file=output)

        for check in issue.checks:
            check_label, check_color, marker = status_visual(check.status)
            marker_text = palette.wrap(BOLD + check_color, marker)
            name_text = palette.wrap(BOLD + check_color, check.name)
            state_text = palette.wrap(BOLD + check_color, check_label)
            print(f"{marker_text} {name_text}  {state_text}", file=output)
            print(f"    {check.detail}", file=output)
            for evidence in check.evidence:
                print(f"    {palette.wrap(DIM, '↳ ' + evidence)}", file=output)
    print(file=output)


def count_issue_statuses(report: Report) -> dict[str, int]:
    """Count derived issue states for the compact headline summary."""
    counts = dict.fromkeys(STATUSES, 0)
    for issue in report.issues:
        counts[derive_issue_status(issue)] += 1
    return counts


def sorted_issues(issues: tuple[Issue, ...]) -> list[Issue]:
    """Put active work first, untouched work second, and completed work last."""
    return sorted(
        issues,
        key=lambda issue: (STATUS_ORDER[derive_issue_status(issue)], issue.issue_id),
    )


def render_table(
    output: TextIO,
    issues: tuple[Issue, ...],
    palette: Palette,
    width: int,
) -> None:
    """Render every issue once in a compact three-column summary table."""
    ordered = sorted_issues(issues)
    id_width = max(10, min(20, max(len(issue.issue_id) for issue in ordered)))
    state_width = len("NOT STARTED")
    summary_width = max(30, width - id_width - state_width - 4)

    print(
        f"{palette.wrap(BOLD, 'ISSUE'.ljust(id_width))}  "
        f"{palette.wrap(BOLD, 'STATUS'.ljust(state_width))}  "
        f"{palette.wrap(BOLD, 'SUMMARY')}",
        file=output,
    )
    print("─" * (id_width + state_width + summary_width + 4), file=output)

    for issue in ordered:
        status = derive_issue_status(issue)
        state_label, state_color, _ = status_visual(status)
        lines = wrap_text(issue.summary, summary_width)
        for index, line in enumerate(lines):
            if index == 0:
                issue_id = issue.issue_id.ljust(id_width)
                state = palette.wrap(BOLD + state_color, state_label.ljust(state_width))
            else:
                issue_id = " " * id_width
                state = " " * state_width
            print(f"{issue_id}  {state}  {line}", file=output)


def wrap_text(value: str, width: int) -> list[str]:
    """Wrap summaries without splitting words or requiring layout hints in JSON."""
    return textwrap.wrap(
        " ".join(value.split()),
        width=width,
        break_long_words=False,
        break_on_hyphens=False,
    ) or [""]


if __name__ == "__main__":
    raise SystemExit(main())
