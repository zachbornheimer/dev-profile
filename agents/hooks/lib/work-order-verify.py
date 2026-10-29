#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""SubagentStop-side half of the structured work-order protocol: scope
enforcement (declared allowed_writes vs actual git diff) and harness-run
acceptance, per skills/prompt-writer/references/work-order-protocol.md.

Correlation problem this solves: PreToolUse (work-order-gate.sh) computes
order_id and writes state/work-orders/<order_id>.json BEFORE the subagent
(and its agent_id) exist, so there is no agent_id to key the mapping by at
spawn time. work-order-gate.sh's compiled header instead embeds
"work-order-id: <order_id>" as a YAML comment inside the fenced block it
sends the worker — durable in the subagent's OWN transcript. This script
reads that transcript (agent_transcript_path, confirmed present on
SubagentStop input since Claude Code 2.0.42) and greps its first `user`
turn for the marker, which also carries the worktree `cwd` Claude Code
records per transcript line — giving both the order and the worktree path
from data this hook is actually handed, with no guess at an undocumented
field.

Entry point: reads a JSON envelope on stdin {"agent_transcript_path":...,
"state_orders_dir":..., "agent_id":...}, prints one JSON result object.

This script only RECORDS the verification (into
state/work-orders/<order_id>.json, keyed by agent_id so a repeat call for
the same finished worker is a no-op — see `_existing_verification`). It
never emits SubagentStop `additionalContext`: per Claude Code's hooks
reference, that field "keeps the subagent running", so feeding it a report
here would resume an already-finished worker instead of ending its turn
(this is exactly what happened before work-order-verify.sh stopped
emitting it — see git history). Delivering the recorded verification to
the ORCHESTRATOR is work-order-report.py's job, invoked from a separate
PostToolUse hook on the Agent tool call, whose `additionalContext` reaches
the parent session instead.
"""

from __future__ import annotations

import fnmatch
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ORDER_ID_RE = None


def _order_id_pattern():
    import re

    global ORDER_ID_RE
    if ORDER_ID_RE is None:
        ORDER_ID_RE = re.compile(r"work-order-id:\s*([0-9a-f]{64})")
    return ORDER_ID_RE


def _message_text(message: dict) -> str:
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "\n".join(parts)
    return ""


def _find_order_id_and_cwd(transcript_path: Path) -> tuple[str | None, str | None]:
    pattern = _order_id_pattern()
    try:
        with transcript_path.open() as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if entry.get("type") != "user":
                    continue
                text = _message_text(entry.get("message", {}))
                match = pattern.search(text)
                if match:
                    return match.group(1), entry.get("cwd")
    except OSError:
        return None, None
    return None, None


def _git(worktree: str, *args: str) -> tuple[int, str]:
    try:
        result = subprocess.run(
            ["git", "-C", worktree, *args],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, str(exc)
    return result.returncode, result.stdout


def _default_branch_base(worktree: str) -> str | None:
    code, out = _git(worktree, "symbolic-ref", "refs/remotes/origin/HEAD")
    if code == 0 and out.strip():
        return out.strip().rsplit("/", 1)[-1]
    for candidate in ("main", "master"):
        code, _ = _git(worktree, "rev-parse", "--verify", candidate)
        if code == 0:
            return candidate
    return None


def _changed_paths(worktree: str) -> list[str]:
    changed: set[str] = set()
    base = _default_branch_base(worktree)
    if base:
        code, out = _git(worktree, "diff", "--name-only", f"{base}...HEAD")
        if code == 0:
            changed.update(p for p in out.splitlines() if p)
    code, out = _git(worktree, "status", "--porcelain", "--untracked-files=all")
    if code == 0:
        for line in out.splitlines():
            if len(line) > 3:
                changed.add(line[3:].strip())
    return sorted(changed)


def _undeclared_writes(changed: list[str], allowed_writes: list[str]) -> list[str]:
    undeclared = []
    for path in changed:
        if not any(fnmatch.fnmatchcase(path, pattern) for pattern in allowed_writes):
            undeclared.append(path)
    return undeclared


def _run_acceptance(worktree: str, item: dict) -> dict:
    run_cmd = item["run"]
    expect = item.get("expect", {})
    try:
        result = subprocess.run(
            run_cmd,
            shell=True,
            cwd=worktree,
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
        )
        exit_code, stdout = result.returncode, result.stdout
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"id": item["id"], "run": run_cmd, "passed": False, "reason": str(exc)}

    failures = []
    if "exit_code" in expect and exit_code != expect["exit_code"]:
        failures.append(f"exit_code {exit_code} != expected {expect['exit_code']}")
    for needle in expect.get("stdout_contains", []):
        if needle not in stdout:
            failures.append(f"stdout missing {needle!r}")
    if "json_keys_absent" in expect:
        try:
            parsed = json.loads(stdout)
        except json.JSONDecodeError:
            failures.append("stdout is not valid JSON, cannot check json_keys_absent")
        else:
            present = [
                k
                for k in expect["json_keys_absent"]
                if isinstance(parsed, dict) and k in parsed
            ]
            if present:
                failures.append(f"json keys present that must be absent: {present}")

    return {
        "id": item["id"],
        "run": run_cmd,
        "exit_code": exit_code,
        "stdout_excerpt": stdout[:2000],
        "passed": not failures,
        "failures": failures,
    }


def _existing_verification(order_state: dict, agent_id: str | None) -> dict | None:
    """Returns the already-recorded verification for `agent_id`, if any.

    Correlation key: a finished subagent that gets resumed (by any hook
    output, a retry, or a resumed session) fires SubagentStop again for the
    SAME agent_id. Re-running acceptance commands on every repeat is wasted
    work at best and a false "still failing" signal at worst if the
    acceptance command has side effects — so a second call for an agent_id
    already present in `verifications` returns the FIRST recorded result
    instead of recomputing it.
    """
    if not agent_id:
        return None
    for record in order_state.get("verifications", []):
        if record.get("agent_id") == agent_id:
            return record
    return None


def verify() -> dict:
    envelope = json.loads(sys.stdin.read() or "{}")
    transcript_path_raw = envelope.get("agent_transcript_path") or ""
    state_orders_dir = Path(envelope.get("state_orders_dir") or "")
    agent_id = envelope.get("agent_id") or None

    if not transcript_path_raw:
        return {
            "applicable": False,
            "reason": "no agent_transcript_path on SubagentStop input",
        }
    transcript_path = Path(transcript_path_raw)
    order_id, worktree = _find_order_id_and_cwd(transcript_path)
    if not order_id:
        return {"applicable": False, "reason": "no work-order-id marker in transcript"}

    order_file = state_orders_dir / f"{order_id}.json"
    if not order_file.exists():
        return {"applicable": False, "reason": f"no state file for order_id={order_id}"}
    order_state = json.loads(order_file.read_text())

    existing = _existing_verification(order_state, agent_id)
    if existing is not None:
        return {
            "applicable": True,
            "order_id": order_id,
            "already_verified": True,
            **existing,
        }

    if not worktree:
        return {
            "applicable": True,
            "order_id": order_id,
            "error": "could not determine worktree path from transcript cwd",
        }

    allowed_writes = (
        order_state.get("work_order", {})
        .get("work_order", {})
        .get("scope", {})
        .get("allowed_writes", [])
    )
    changed = _changed_paths(worktree)
    undeclared = _undeclared_writes(changed, allowed_writes)

    acceptance_items = (
        order_state.get("work_order", {}).get("work_order", {}).get("acceptance", [])
    )
    acceptance_results = [_run_acceptance(worktree, item) for item in acceptance_items]

    verification_record = {
        "agent_id": agent_id,
        "verified_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "worktree": worktree,
        "changed_paths": changed,
        "undeclared_writes": undeclared,
        "acceptance_results": acceptance_results,
    }
    order_state.setdefault("verifications", []).append(verification_record)
    order_file.write_text(json.dumps(order_state, indent=2, sort_keys=True))

    return {
        "applicable": True,
        "order_id": order_id,
        **verification_record,
    }


def main() -> int:
    print(json.dumps(verify()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
