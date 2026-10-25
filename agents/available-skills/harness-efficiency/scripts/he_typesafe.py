"""TypeSafe overlay for harness-efficiency signal findings."""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

TYPESAFE_CLI = (
    Path.home() / ".agents" / "skills" / "typesafe-ai" / "scripts" / "typesafe.py"
)
TICKETS_PATH = Path(__file__).resolve().parent.parent / "references" / "linear_tickets.json"
CLASSIFY_COMMAND = "classify-findings"
TYPESAFE_TIMEOUT_SECONDS = 15
SIGNAL_SESSION_COUNT = 50
SIGNAL_KINDS = frozenset(
    {
        "retry",
        "long_session",
        "permission_stop",
        "instruction_bloat",
        "model_routing",
        "subagent",
    }
)
SOURCE_TYPESAFE = "typesafe"
OVERLAY_FIELDS = ("typesafe_action", "typesafe_primitive", "typesafe_source")

RunCLI = Callable[[list[str], str, float], subprocess.CompletedProcess[str]]


def is_signal_finding(finding: Mapping[str, Any]) -> bool:
    if int(finding.get("session_count") or 0) >= SIGNAL_SESSION_COUNT:
        return True
    return str(finding.get("kind") or "") in SIGNAL_KINDS


def load_tickets(path: Path) -> list[Any]:
    if not path.is_file():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return []
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and isinstance(payload.get("tickets"), list):
        return payload["tickets"]
    return []


def parse_overlays(raw: str) -> dict[str, dict[str, Any]]:
    payload = json.loads(raw)
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict) and isinstance(payload.get("findings"), list):
        rows = payload["findings"]
    else:
        return {}
    overlays: dict[str, dict[str, Any]] = {}
    for row in rows:
        if isinstance(row, dict) and row.get("id"):
            overlays[str(row["id"])] = row
    return overlays


def apply_overlay(finding: dict[str, Any], overlay: Mapping[str, Any]) -> None:
    for field in OVERLAY_FIELDS:
        if field in overlay and overlay[field] is not None:
            finding[field] = overlay[field]
    primitive = finding.get("typesafe_primitive")
    if primitive and finding.get("typesafe_source") == SOURCE_TYPESAFE:
        finding["canned_primitive"] = finding.get("proposed_primitive")
        finding["proposed_primitive"] = primitive


def run_cli(
    argv: list[str], stdin: str, timeout: float
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        input=stdin,
        timeout=timeout,
        capture_output=True,
        text=True,
        check=False,
    )


def classify_signal_findings(
    findings: list[dict[str, Any]],
    *,
    cli_path: Path | None = None,
    tickets_path: Path | None = None,
    run: RunCLI | None = None,
    timeout: float = TYPESAFE_TIMEOUT_SECONDS,
) -> list[dict[str, Any]]:
    path = TYPESAFE_CLI if cli_path is None else cli_path
    if not path.is_file():
        return findings
    signal = [item for item in findings if is_signal_finding(item)]
    if not signal:
        return findings
    tickets = load_tickets(TICKETS_PATH if tickets_path is None else tickets_path)
    runner = run_cli if run is None else run
    stdin = json.dumps({"findings": signal, "tickets": tickets})
    argv = [sys.executable, str(path), CLASSIFY_COMMAND]
    try:
        completed = runner(argv, stdin, timeout)
    except (OSError, subprocess.TimeoutExpired):
        return findings
    if completed.returncode != 0:
        return findings
    try:
        overlays = parse_overlays(completed.stdout or "")
    except (json.JSONDecodeError, TypeError, ValueError):
        return findings
    for finding in findings:
        overlay = overlays.get(str(finding.get("id") or ""))
        if overlay:
            apply_overlay(finding, overlay)
    return findings
