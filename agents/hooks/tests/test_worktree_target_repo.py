"""The worktree follows the work order's TARGET repo, not the session's
(formerly tests/worktree-provision-target-repo.sh).

work-order-gate.py (PreToolUse:Agent) queues the order's target repo under
the session id; worktree-provision.py (WorktreeCreate) claims it. Every
repo here is a throwaway under tmp_path.

  (a) session repo A, order targets repo B -> worktree at B's canonical
      path on a B branch; Claude Code's stray pre-created A worktree and
      its empty branch are removed.
  (b) order targets A -> unchanged canonical A worktree.
  (c) targets span A and B -> gate denies, asking to split the order.
  (d) no queued record -> session-cwd fallback, unchanged.
  (e) stale record -> ignored and expired; session-cwd fallback.
  (f) target inside B's linked worktree (.worktrees/B-x/new-file) ->
      worktree provisioned from B's main repo.
  (h) a worktree on the wrong branch is refused, never handed back.

Case (g) from the former .sh (gate SIGTERM'd mid-validation) exercised a
shell-only timing seam and was itself skipped for the .py variant there.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest
from hook_harness import HOOKS_DIR

GATE = "work-order-gate.py"
PROVISION = "worktree-provision.py"
STALE_MTIME = "1"


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


def _env(state_dir: Path, **extra: str) -> dict[str, str]:
    return {
        "HOME": os.environ["HOME"],
        "PATH": os.environ["PATH"],
        "TMPDIR": os.environ.get("TMPDIR", "/tmp"),
        "HC_STATE_DIR_OVERRIDE": str(state_dir),
        **extra,
    }


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
        env=_env(state_dir),
        timeout=30,
        check=False,
    )
    return json.loads(done.stdout) if done.stdout.strip() else {}


def run_provision(
    state_dir: Path, session_id: str, cwd: Path, name: str, **env_extra: str
) -> str:
    payload = {
        "session_id": session_id,
        "cwd": str(cwd),
        "hook_event_name": "WorktreeCreate",
        "name": name,
    }
    done = subprocess.run(
        [str(HOOKS_DIR / PROVISION)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=_env(state_dir, **env_extra),
        timeout=30,
        check=False,
    )
    lines = [line for line in done.stdout.splitlines() if line.strip()]
    return lines[-1] if lines else ""


def decision_of(gate_output: dict) -> str:
    return (gate_output.get("hookSpecificOutput") or {}).get(
        "permissionDecision", "none"
    )


def on_branch(repo: Path, worktree_path: str, branch: str) -> bool:
    result = subprocess.run(
        ["git", "-C", str(repo), "worktree", "list", "--porcelain"],
        capture_output=True,
        text=True,
        check=False,
    )
    at_path = False
    for line in result.stdout.splitlines():
        if line.startswith("worktree "):
            at_path = line[len("worktree ") :] == worktree_path
        elif at_path and line == f"branch refs/heads/{branch}":
            return True
    return False


def test_cross_repo_target_claims_b(tmp_path: Path, repos: tuple[Path, Path]) -> None:
    repo_a, repo_b = repos
    state = tmp_path / "state"
    name = "agent-cross1"
    stray = repo_a / ".claude" / "worktrees" / name
    stray.parent.mkdir(parents=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(repo_a),
            "worktree",
            "add",
            "--quiet",
            "-b",
            f"worktree-{name}",
            str(stray),
        ],
        check=True,
        capture_output=True,
    )

    gate_out = run_gate(state, "sid-a", repo_a, repo_b / "seed.txt")
    assert decision_of(gate_out) == "allow", gate_out

    got = run_provision(state, "sid-a", repo_a, name)
    want = str(tmp_path / "orgB" / ".worktrees" / f"beta-{name}")
    assert got == want
    assert on_branch(repo_b, want, f"worktree-{name}")
    assert not stray.exists()  # stray A worktree removed
    branch_exists = subprocess.run(
        [
            "git",
            "-C",
            str(repo_a),
            "show-ref",
            "--verify",
            "--quiet",
            f"refs/heads/worktree-{name}",
        ],
        check=False,
    ).returncode
    assert branch_exists != 0  # empty A branch deleted


def test_target_is_session_repo_unchanged(
    tmp_path: Path, repos: tuple[Path, Path]
) -> None:
    repo_a, _ = repos
    state = tmp_path / "state"
    name = "agent-same1"

    gate_out = run_gate(state, "sid-b", repo_a, repo_a / "seed.txt")
    assert decision_of(gate_out) == "allow", gate_out

    got = run_provision(state, "sid-b", repo_a, name)
    want = str(tmp_path / "orgA" / ".worktrees" / f"alpha-{name}")
    assert got == want
    assert on_branch(repo_a, want, f"worktree-{name}")


def test_targets_spanning_two_repos_denied(
    tmp_path: Path, repos: tuple[Path, Path]
) -> None:
    repo_a, repo_b = repos
    state = tmp_path / "state"

    gate_out = run_gate(
        state, "sid-c", repo_a, repo_a / "seed.txt", repo_b / "seed.txt"
    )
    reason = (gate_out.get("hookSpecificOutput") or {}).get(
        "permissionDecisionReason", ""
    )
    assert decision_of(gate_out) == "deny", gate_out
    assert "targets_span_repos" in reason
    assert "Split" in reason
    assert (
        not list((state / "worktree-targets" / "sid-c").glob("*"))
        if (state / "worktree-targets" / "sid-c").exists()
        else True
    )


def test_no_queued_record_falls_back_to_session_repo(
    tmp_path: Path, repos: tuple[Path, Path]
) -> None:
    repo_a, _ = repos
    state = tmp_path / "state"
    name = "agent-norecord"

    got = run_provision(state, "sid-d", repo_a, name)
    assert got == str(tmp_path / "orgA" / ".worktrees" / f"alpha-{name}")


def test_stale_record_ignored_and_expired(
    tmp_path: Path, repos: tuple[Path, Path]
) -> None:
    repo_a, repo_b = repos
    state = tmp_path / "state"
    name = "agent-stale"

    run_gate(state, "sid-e", repo_a, repo_b / "seed.txt")
    records = list((state / "worktree-targets" / "sid-e").glob("*.repo"))
    assert records
    stale = records[0]
    mtime_env_name = "HC_FILE_MTIME_OVERRIDE_" + "".join(
        c if c.isalnum() or c == "_" else "_" for c in str(stale)
    )

    got = run_provision(state, "sid-e", repo_a, name, **{mtime_env_name: STALE_MTIME})

    assert got == str(tmp_path / "orgA" / ".worktrees" / f"alpha-{name}")


def test_target_inside_linked_worktree_resolves_to_main_repo(
    tmp_path: Path, repos: tuple[Path, Path]
) -> None:
    repo_a, repo_b = repos
    state = tmp_path / "state"
    name = "agent-linked"
    linked = tmp_path / "orgB" / ".worktrees" / "beta-proof"
    subprocess.run(
        [
            "git",
            "-C",
            str(repo_b),
            "worktree",
            "add",
            "--quiet",
            "-b",
            "proof",
            str(linked),
        ],
        check=True,
        capture_output=True,
    )

    gate_out = run_gate(state, "sid-f", repo_a, linked / "new" / "dir" / "file.txt")
    assert decision_of(gate_out) == "allow", gate_out

    got = run_provision(state, "sid-f", repo_a, name)
    want = str(tmp_path / "orgB" / ".worktrees" / f"beta-{name}")
    assert got == want
    assert on_branch(repo_b, want, f"worktree-{name}")


def test_wrong_branch_worktree_is_refused(
    tmp_path: Path, repos: tuple[Path, Path]
) -> None:
    repo_a, _ = repos
    state = tmp_path / "state"
    name = "agent-wrongbranch"
    dest = tmp_path / "orgA" / ".worktrees" / f"alpha-{name}"
    dest.parent.mkdir(parents=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(repo_a),
            "worktree",
            "add",
            "--quiet",
            "-b",
            "stale-branch",
            str(dest),
        ],
        check=True,
        capture_output=True,
    )

    payload = {"session_id": "sid-h", "cwd": str(repo_a), "name": name}
    done = subprocess.run(
        [str(HOOKS_DIR / PROVISION)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=_env(state),
        timeout=30,
        check=False,
    )

    assert done.returncode != 0
    assert str(dest) not in done.stdout.splitlines()
