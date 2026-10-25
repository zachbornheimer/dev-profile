"""work-order-verify record-then-repeat and work-order-report relay-then-suppress
(formerly run.sh 9b-9c)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from hook_harness import HookRun, HookRunner, HookSession
from test_work_order_flows import ORDERS_DIR, assert_clean, make_repo, run_git

VERIFY = "work-order-verify.py"
REPORT = "work-order-report.py"
AGENT_ID = "hgtest-agent-1"


@dataclass(frozen=True, slots=True)
class FinishedWorker:
    """A worker that wrote outside its order and failed acceptance, as run.sh 9b built it."""

    order_id: str
    order_record: str
    parent_transcript: Path

    @property
    def verify_payload(self) -> dict[str, str]:
        agent_transcript = (
            self.parent_transcript.with_suffix("")
            / "subagents"
            / f"agent-{AGENT_ID}.jsonl"
        )
        return {"agent_transcript_path": str(agent_transcript), "agent_id": AGENT_ID}

    @property
    def report_payload(self) -> dict[str, Any]:
        return {
            "transcript_path": str(self.parent_transcript),
            "tool_name": "Agent",
            "tool_response": {"status": "completed", "agentId": AGENT_ID},
        }

    def seed(self, session: HookSession) -> None:
        session.write(f"{ORDERS_DIR}/{self.order_id}.json", self.order_record)


@pytest.fixture
def worker(tmp_path: Path) -> FinishedWorker:
    repo = make_repo(tmp_path / "repo")
    (repo / "allowed.go").write_text("package main\n// change\n")
    (repo / "not_allowed.go").write_text("package main\n")
    run_git(repo, "add", "-A")
    order_id = "a" * 64
    parent = tmp_path / "parent.jsonl"
    parent.write_text("")
    agent_transcript = tmp_path / "parent" / "subagents" / f"agent-{AGENT_ID}.jsonl"
    agent_transcript.parent.mkdir(parents=True)
    content = f"```yaml\n# work-order-id: {order_id}\nwork_order: {{}}\n```"
    agent_transcript.write_text(
        json.dumps({"type": "user", "cwd": str(repo), "message": {"content": content}})
        + "\n"
    )
    record = {
        "work_order": {
            "work_order": {
                "scope": {"allowed_writes": ["allowed.go"]},
                "acceptance": [
                    {
                        "id": "should-fail",
                        "kind": "command",
                        "run": "exit 3",
                        "expect": {"exit_code": 0},
                    }
                ],
            }
        }
    }
    return FinishedWorker(order_id, json.dumps(record) + "\n", parent)


def verification_summary(
    session: HookSession, worker: FinishedWorker
) -> list[tuple[Any, ...]]:
    """The recorded verifications, minus timings, which differ run to run."""
    record = json.loads(
        (session.state_dir / ORDERS_DIR / f"{worker.order_id}.json").read_text()
    )
    return [
        (
            item.get("agent_id"),
            sorted(item.get("changed_paths", [])),
            [(a["id"], a["passed"]) for a in item["acceptance_results"]],
        )
        for item in record.get("verifications", [])
    ]


def assert_clean_run(run: HookRun) -> None:
    assert_clean(run)


def test_verify_record_then_repeat(hooks: HookRunner, worker: FinishedWorker) -> None:
    session = hooks.session(VERIFY)
    worker.seed(session)

    for _ in range(2):
        run = session.run_payload(VERIFY, worker.verify_payload)
        assert_clean_run(run)
        assert run.stdout == ""  # never resumes the worker
    assert len(verification_summary(session, worker)) == 1


def test_report_relay_then_suppress(hooks: HookRunner, worker: FinishedWorker) -> None:
    session = hooks.session(REPORT)
    worker.seed(session)
    session.run_payload(VERIFY, worker.verify_payload)

    relay = session.run_payload(REPORT, worker.report_payload)
    assert_clean_run(relay)
    assert "should-fail=FAIL" in relay.output["hookSpecificOutput"]["additionalContext"]

    repeat = session.run_payload(REPORT, worker.report_payload)
    assert_clean_run(repeat)
    assert repeat.stdout == ""
