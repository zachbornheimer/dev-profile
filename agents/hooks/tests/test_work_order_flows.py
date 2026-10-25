"""work-order-gate's repair-by-reference flow (formerly run.sh 9a).

Deny, then resend only a fragment under order_ref, in one live session so
each step reads the state the previous step wrote. Verify/report flows
live in test_work_order_verification_flows.py and reuse this file's
helpers.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

import pytest
from hook_harness import FIXTURES_DIR, HookRun, HookRunner, HookSession

GATE = "work-order-gate.py"
SESSION_ID = "hgtest-flow"
ORDERS_DIR = "work-orders"
PENDING_DIR = "work-orders/pending"
WORKTREE_TARGETS_DIR = "worktree-targets"
EXPIRED_MTIME = "1"
GIT_IDENTITY = ("-c", "user.email=hgtest@example.com", "-c", "user.name=hgtest")

NO_FENCE_PROMPT = (
    "Add the clarify feedback field for scoped runner arguments, no fence on purpose."
)
REPAIR_FENCE = """```yaml
work_order:
  schema_version: 1
  intent: "Preserve scoped args through the repair-by-reference flow."
  scope:
    primary_targets:
      - README.md
    allowed_writes:
      - README.md
  acceptance:
    - id: t
      kind: command
      run: echo hi
      expect:
        exit_code: 0
```"""
BAD_PATCH = "```work_order_patch\nnot valid json\n```"
GOOD_PATCH = (
    "```work_order_patch\n"
    '[{"op": "add", "path": "/work_order/acceptance", "value": [{"id": "t", "kind": "command", '
    '"run": "echo hi", "expect": {"exit_code": 0}}]}]\n'
    "```"
)


def run_git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def make_repo(root: Path) -> Path:
    """A throwaway git repo: the spawn's cwd, and the worker's worktree for verify."""
    root.mkdir()
    run_git(root, "init", "-q", "-b", "main")
    (root / "README.md").write_text("seed\n")
    (root / "allowed.go").write_text("package main\n")
    run_git(root, "add", "-A")
    run_git(root, *GIT_IDENTITY, "commit", "-q", "-m", "test: seed fixture repo")
    return root


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    return make_repo(tmp_path / "repo")


def spawn(prompt: str, cwd: Path) -> dict[str, Any]:
    return {
        "session_id": SESSION_ID,
        "tool_name": "Agent",
        "cwd": str(cwd),
        "tool_input": {
            "subagent_type": "implement",
            "isolation": "worktree",
            "prompt": prompt,
        },
    }


def resend(ref: str, fragment: str) -> str:
    return f"order_ref: {ref}\n\n{fragment}"


def order_ref(run: HookRun) -> str:
    return json.loads(run.output["hookSpecificOutput"]["permissionDecisionReason"]).get(
        "order_ref", ""
    )


def assert_clean(run: HookRun) -> None:
    assert run.exit_code == 0
    assert run.stderr == ""
    assert not run.failed_open, run.log


def state_files(session: HookSession, subdir: str) -> dict[str, str]:
    """Relative path -> content for every file under ``subdir`` (the next call's input)."""
    root = session.state_dir / subdir
    return {
        str(p.relative_to(root)): p.read_text()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def queued_records(session: HookSession) -> list[str]:
    return sorted(state_files(session, WORKTREE_TARGETS_DIR).values())


# --- gate: repair-by-reference ------------------------------------------------


def test_repair_by_fence(hooks: HookRunner, repo: Path) -> None:
    session = hooks.session(GATE)

    deny = session.run_payload(GATE, spawn(NO_FENCE_PROMPT, repo))
    assert_clean(deny)
    assert deny.decision == "deny"
    assert queued_records(session) == []  # deny drops the queued target

    allow = session.run_payload(
        GATE, spawn(resend(order_ref(deny), REPAIR_FENCE), repo)
    )
    assert_clean(allow)
    assert allow.decision == "allow"
    assert (
        NO_FENCE_PROMPT in allow.output["hookSpecificOutput"]["updatedInput"]["prompt"]
    )
    assert (
        state_files(session, PENDING_DIR) == {}
    )  # a repaired order is done being repaired
    assert queued_records(session) != []


def test_missing_acceptance_repairs_by_pasting_the_example_file(
    hooks: HookRunner, repo: Path
) -> None:
    session = hooks.session(GATE)
    schema_failure = json.loads(
        (FIXTURES_DIR / "work-order-gate-missing-acceptance-deny.json").read_text()
    )
    prompt = schema_failure["tool_input"]["prompt"]

    deny = session.run_payload(GATE, spawn(prompt, repo))
    assert_clean(deny)
    body = json.loads(deny.output["hookSpecificOutput"]["permissionDecisionReason"])
    fragment = Path(body["example_path"]).read_text()

    allow = session.run_payload(GATE, spawn(resend(body["order_ref"], fragment), repo))
    assert_clean(allow)
    assert allow.decision == "allow"


def test_bad_patch_then_good_patch(hooks: HookRunner, repo: Path) -> None:
    session = hooks.session(GATE)
    schema_failure = json.loads(
        (FIXTURES_DIR / "work-order-gate-missing-acceptance-deny.json").read_text()
    )
    prompt = schema_failure["tool_input"]["prompt"]

    run = session.run_payload(GATE, spawn(prompt, repo))
    assert_clean(run)
    ref = order_ref(run)

    for fragment in (BAD_PATCH, GOOD_PATCH):
        run = session.run_payload(GATE, spawn(resend(ref, fragment), repo))
        assert_clean(run)
    assert run.decision == "allow"


def test_expired_pending_order(hooks: HookRunner, repo: Path) -> None:
    session = hooks.session(GATE)
    run = session.run_payload(
        GATE, spawn("Expiry test prompt with no fence and no legacy markers.", repo)
    )
    ref = order_ref(run)

    pending = session.state_dir / PENDING_DIR / f"{ref}.txt"
    backdated = {
        "HC_FILE_MTIME_OVERRIDE_"
        + re.sub(r"[^A-Za-z0-9_]", "_", str(pending)): EXPIRED_MTIME
    }

    payload = spawn(resend(ref, "```yaml\nwork_order: {}\n```"), repo)
    run = session.run_payload(GATE, payload, backdated)

    assert_clean(run)
    body = json.loads(run.output["hookSpecificOutput"]["permissionDecisionReason"])
    assert list(body) == ["order_ref", "missing", "example_path"]
    assert Path(body["example_path"]).read_text().strip() == "expired"
    assert state_files(session, PENDING_DIR) == {}
