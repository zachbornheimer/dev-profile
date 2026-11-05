#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Assert an omp session's startup context carries no duplicate capability aliases.

Reads the newest omp session JSONL and reports, as findings:

  duplicate-alias   a mounted tool whose name repeats another mount's tool
  unreachable       no enabled MCP server supplies the command runner

Modes:
  (default)         report findings, exit 1 when any exist
  --expect-deduped  the regression gate: exit 0 only when there are no findings
  --self-test       run the assertions against built-in fixtures that must fail
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

SESSIONS = Path.home() / ".omp/agent/sessions"
MCP_CONFIG = Path.home() / ".omp/agent/mcp.json"
ALWAYS_ON = "mcp__capability_always_on_"
CANONICAL = "mcp__capability_"
TOOL_LINE_RE = re.compile(r"^- xd://([A-Za-z0-9_:.-]+)")


@dataclass(frozen=True, slots=True)
class Finding:
    kind: str
    detail: str


def newest_session(root: Path = SESSIONS) -> Path | None:
    files = sorted(root.glob("*/*.jsonl"), key=lambda p: p.stat().st_mtime)
    return files[-1] if files else None


def custom_messages(session: Path) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for line in session.read_text(errors="ignore").splitlines():
        if '"custom_message"' not in line:
            continue
        try:
            record = json.loads(line)
        except ValueError:
            continue
        content = record.get("content")
        if record.get("type") == "custom_message" and isinstance(content, str):
            out.append((str(record.get("customType", "")), content))
    return out


def duplicate_aliases(notice: str) -> list[Finding]:
    """An always-on mount repeating a name the full capability mount already serves."""
    names = [m.group(1) for m in map(TOOL_LINE_RE.match, notice.splitlines()) if m]
    canonical = {
        n for n in names if n.startswith(CANONICAL) and not n.startswith(ALWAYS_ON)
    }
    findings = []
    for name in names:
        if not name.startswith(ALWAYS_ON):
            continue
        twin = CANONICAL + name[len(ALWAYS_ON) :]
        if twin in canonical:
            findings.append(Finding("duplicate-alias", f"{name} duplicates {twin}"))
    return findings


def command_runner_reachable(config: Path) -> list[Finding]:
    """The command runner must come from an enabled server after any mount is removed."""
    try:
        doc = json.loads(config.read_text())
    except (OSError, ValueError) as exc:
        return [Finding("unreachable", f"{config}: {exc}")]
    disabled = set(doc.get("disabledServers") or [])
    enabled = [
        name
        for name, spec in (doc.get("mcpServers") or {}).items()
        if isinstance(spec, dict) and spec.get("enabled", True) and name not in disabled
    ]
    if not enabled:
        return [Finding("unreachable", "no enabled MCP server in mcp.json")]
    return []


def inspect(session: Path, config: Path = MCP_CONFIG) -> list[Finding]:
    messages = custom_messages(session)
    notices = [c for kind, c in messages if kind == "xdev-mount-notice"]
    findings: list[Finding] = []
    for notice in notices:
        findings.extend(duplicate_aliases(notice))
    findings.extend(command_runner_reachable(config))
    return findings


SELF_TEST_LINES = [
    # must fail: an always-on alias beside its canonical twin
    '{"type":"custom_message","customType":"xdev-mount-notice","content":"<system-notice>\\n- xd://mcp__capability_run_command — runner\\n- xd://mcp__capability_always_on_run_command — runner\\n</system-notice>"}',
    # must pass: a unique always-on tool
    '{"type":"custom_message","customType":"xdev-mount-notice","content":"- xd://mcp__capability_run_command — runner\\n- xd://mcp__capability_always_on_extra — unique"}',
]


def self_test(workdir: Path, config: Path = MCP_CONFIG) -> int:
    bad = workdir / "bad.jsonl"
    good = workdir / "good.jsonl"
    bad.write_text("\n".join(SELF_TEST_LINES[:1]) + "\n")
    good.write_text("\n".join(SELF_TEST_LINES[1:]) + "\n")
    failures = [finding.kind for finding in inspect(bad, config)]
    if "duplicate-alias" not in failures:
        print(
            f"self-test failed: duplicated fixture reported {failures}", file=sys.stderr
        )
        return 1
    clean = [finding.kind for finding in inspect(good, config)]
    if clean:
        print(f"self-test failed: deduped fixture reported {clean}", file=sys.stderr)
        return 1
    print("self-test passed: duplicated fixture fails, deduped fixture passes")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--expect-deduped", action="store_true", help="exit 0 only with no findings"
    )
    mode.add_argument(
        "--self-test", action="store_true", help="assert the checks can fail"
    )
    parser.add_argument("--session", type=Path, help="session JSONL to inspect")
    parser.add_argument(
        "--fixtures", type=Path, default=Path("/tmp"), help="self-test workdir"
    )
    parser.add_argument(
        "--only",
        action="append",
        choices=["duplicate-alias", "unreachable"],
        help="assert on one finding kind alone (repeatable)",
    )
    args = parser.parse_args()

    if args.self_test:
        return self_test(args.fixtures)

    session = args.session or newest_session()
    if session is None:
        print(f"no omp session JSONL under {SESSIONS}", file=sys.stderr)
        return 2
    findings = inspect(session)
    if args.only:
        findings = [finding for finding in findings if finding.kind in args.only]
    print(f"session {session.name}")
    for finding in findings:
        print(f"  {finding.kind}: {finding.detail}")
    print(f"{len(findings)} finding(s)")
    return (1 if findings else 0) if args.expect_deduped else 0


if __name__ == "__main__":
    raise SystemExit(main())
