#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# ///
"""Smoke tests for the status-report renderer."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RENDERER = ROOT / "scripts" / "render.py"
EXAMPLE = ROOT / "examples" / "zys-1540.json"
SAH_EXAMPLE = ROOT / "examples" / "sah-9395.json"
ESC = "\x1b["


def run_renderer(report: dict, *args: str) -> subprocess.CompletedProcess[str]:
    """Invoke the public inline-JSON interface used by agents."""
    return subprocess.run(
        ["uv", "run", str(RENDERER), *args, "--json", json.dumps(report, separators=(",", ":"))],
        check=False,
        capture_output=True,
        text=True,
    )


def require(condition: bool, message: str) -> None:
    """Fail fast with a readable smoke-test error."""
    if not condition:
        raise AssertionError(message)


def main() -> int:
    """Exercise strict states, derived state, ANSI semantics, and detail headings."""
    report = json.loads(EXAMPLE.read_text(encoding="utf-8"))

    validated = run_renderer(report, "--validate-only")
    require(validated.returncode == 0, validated.stderr)
    require(validated.stdout.strip() == "valid", "validate-only did not return valid")

    plain = run_renderer(report, "--color=never")
    require(plain.returncode == 0, plain.stderr)
    require("STATUS  Sleepy Hollow  IN PROGRESS" in plain.stdout, "wrong derived report state")
    require("ZYS-1540  IN PROGRESS" in plain.stdout, "detail heading does not repeat issue status")
    require("✔ Issue hypothesis  DONE" in plain.stdout, "missing DONE check")
    require("● PR landed  IN PROGRESS" in plain.stdout, "missing IN PROGRESS check")
    require("✘ Fix proven in prod  NOT STARTED" in plain.stdout, "missing NOT STARTED check")
    require("DEFERRED" not in plain.stdout, "deprecated DEFERRED state leaked into output")
    require(ESC not in plain.stdout, "--color=never emitted ANSI escapes")

    colored = run_renderer(report, "--color=always")
    require(colored.returncode == 0, colored.stderr)
    require("\x1b[32m" in colored.stdout, "green DONE output missing")
    require("\x1b[34m" in colored.stdout, "blue IN PROGRESS output missing")
    require("\x1b[31m" in colored.stdout, "red NOT STARTED output missing")

    sah = json.loads(SAH_EXAMPLE.read_text(encoding="utf-8"))
    sah_plain = run_renderer(sah, "--color=never")
    require(sah_plain.returncode == 0, sah_plain.stderr)
    require("SAH-9395  NOT STARTED" in sah_plain.stdout, "SAH detail status missing")
    require("✘ Issue replicated  NOT STARTED" in sah_plain.stdout, "SAH check status missing")

    invalid = json.loads(json.dumps(report))
    invalid["issues"][0]["checks"][0]["status"] = "deferred"
    rejected = run_renderer(invalid, "--validate-only")
    require(rejected.returncode != 0, "deferred status was accepted")
    require("use done, in_progress, or not_started" in rejected.stderr, "unexpected state error")

    legacy_issue_state = json.loads(json.dumps(report))
    legacy_issue_state["issues"][0]["state"] = "done"
    rejected_state = run_renderer(legacy_issue_state, "--validate-only")
    require(rejected_state.returncode != 0, "model-supplied issue state was accepted")

    print("PASS: status-report renderer")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
