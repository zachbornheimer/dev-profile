"""Work orders spanning multiple repositories must be split before spawning."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest
from hook_harness import HOOKS_DIR

GATE = "work-order-gate.py"


def make_repo(root: Path) -> Path:
    root.mkdir(parents=True)
    subprocess.run(["git", "init", "--quiet", str(root)], check=True)
    subprocess.run(
        ["git", "-C", str(root), "config", "user.email", "test@example.invalid"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(root), "config", "user.name", "Worktree Target Test"],
        check=True,
    )
    (root / "seed.txt").write_text("seed\n")
    subprocess.run(["git", "-C", str(root), "add", "seed.txt"], check=True)
    subprocess.run(
        ["git", "-C", str(root), "commit", "--quiet", "-m", "seed"], check=True
    )
    return root


@pytest.fixture
def repos(tmp_path: Path) -> tuple[Path, Path]:
    return make_repo(tmp_path / "orgA" / "alpha"), make_repo(tmp_path / "orgB" / "beta")


def run_gate(state_dir: Path, session_id: str, cwd: Path, *targets: Path) -> dict:
    target_lines = "".join(f"      - {t}\n" for t in targets)
    prompt = (
        '```yaml\nwork_order:\n  schema_version: 1\n  intent: "Edit the target."\n  scope:\n'
        f"    primary_targets:\n{target_lines}    allowed_writes:\n{target_lines}"
        "  acceptance:\n    - id: t\n      kind: command\n      run: echo hi\n      expect:\n        exit_code: 0\n```\n\nDo it."
    )
    payload = {
        "session_id": session_id,
        "tool_name": "Agent",
        "cwd": str(cwd),
        "tool_input": {
            "subagent_type": "implement",
            "isolation": "worktree",
            "model": "haiku",
            "prompt": prompt,
        },
    }
    done = subprocess.run(
        [str(HOOKS_DIR / GATE)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env={
            "HOME": os.environ["HOME"],
            "PATH": os.environ["PATH"],
            "TMPDIR": os.environ.get("TMPDIR", "/tmp"),
            "HC_STATE_DIR_OVERRIDE": str(state_dir),
        },
        timeout=30,
        check=False,
    )
    return json.loads(done.stdout) if done.stdout.strip() else {}


def test_targets_spanning_two_repos_denied(
    tmp_path: Path, repos: tuple[Path, Path]
) -> None:
    repo_a, repo_b = repos
    state = tmp_path / "state"

    gate_out = run_gate(
        state, "sid-c", repo_a, repo_a / "seed.txt", repo_b / "seed.txt"
    )
    output = gate_out.get("hookSpecificOutput") or {}
    reason = output.get("permissionDecisionReason", "")
    assert output.get("permissionDecision", "none") == "deny", gate_out
    assert "targets_span_repos" in reason
    assert "Split" in reason
    assert (
        not list((state / "worktree-targets" / "sid-c").glob("*"))
        if (state / "worktree-targets" / "sid-c").exists()
        else True
    )
