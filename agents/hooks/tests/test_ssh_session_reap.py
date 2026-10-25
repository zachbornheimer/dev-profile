"""ssh-session-reap.py: fixture cases ported from the former tests/ssh-session-reap.sh."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from hook_harness import FIXTURES_DIR, HOOKS_DIR, HookRun

PY_HOOK = "ssh-session-reap.py"

PS_TABLE = """  101     1 /usr/bin/ssh nas docker ps GROK_SESSION_ID=hgtest-ssh-reap
  102     1 /usr/bin/ssh nas docker ps GROK_SESSION_ID=other-session-id
  103     1 /usr/bin/ssh -N -o BatchMode=yes -o ControlPath=/tmp/cm GROK_SESSION_ID=hgtest-ssh-reap
  104     1 /usr/sbin/sshd -D GROK_SESSION_ID=hgtest-ssh-reap
  105   200 /usr/bin/ssh mini hostname
  106     1 /usr/bin/ssh mini hostname
  200     1 /bin/zsh -c builtin export GROK_AGENT=1 GROK_SESSION_ID=hgtest-ssh-reap
"""


@dataclass(frozen=True, slots=True)
class ReapRun:
    hook_run: HookRun
    killed: list[str]


def run_reap(
    hook: str, fixture: str, tmp_path: Path, index: int, self_pids: str = "99999"
) -> ReapRun:
    ps_file = tmp_path / "ps.txt"
    ps_file.write_text(PS_TABLE)
    kill_file = tmp_path / f"kill-{index}.txt"
    kill_file.write_text("")
    state_dir = tmp_path / f"state-{index}"
    state_dir.mkdir()
    env = {
        **os.environ,
        "HC_STATE_DIR_OVERRIDE": str(state_dir),
        "SSH_REAP_PS_FILE": str(ps_file),
        "SSH_REAP_KILL_FILE": str(kill_file),
        "SSH_REAP_SELF_PIDS": self_pids,
    }
    import subprocess

    done = subprocess.run(
        [str(HOOKS_DIR / hook)],
        input=(FIXTURES_DIR / fixture).read_text(),
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
        check=False,
    )
    killed = []
    for line in kill_file.read_text().splitlines():
        if line.startswith("TERM "):
            killed.append(line.split()[1])
    return ReapRun(
        HookRun(done.returncode, done.stdout, done.stderr, ""), sorted(killed, key=int)
    )


def test_stop_reaps_tagged_and_session_parented_ssh(tmp_path: Path) -> None:
    run = run_reap(PY_HOOK, "ssh-reap-stop.json", tmp_path, 1)
    assert run.hook_run.stdout.strip() == ""
    assert run.killed == ["101", "105"]


def test_stop_leaves_protected_pids(tmp_path: Path) -> None:
    run = run_reap(PY_HOOK, "ssh-reap-stop.json", tmp_path, 2)
    assert set(run.killed).isdisjoint({"102", "103", "104", "106", "200"})


def test_post_tool_use_bash_same_reap_set_as_stop(tmp_path: Path) -> None:
    run = run_reap(PY_HOOK, "ssh-reap-post-bash.json", tmp_path, 3)
    assert run.hook_run.stdout.strip() == ""
    assert run.killed == ["101", "105"]


def test_malformed_json_fails_open_with_no_kills(tmp_path: Path) -> None:
    run = run_reap(PY_HOOK, "ssh-reap-malformed.json", tmp_path, 4)
    assert run.hook_run.stdout.strip() == ""
    assert run.killed == []


def test_short_session_id_refuses_to_match(tmp_path: Path) -> None:
    run = run_reap(PY_HOOK, "ssh-reap-short-session.json", tmp_path, 5)
    assert run.hook_run.stdout.strip() == ""
    assert run.killed == []


def test_self_pids_in_protect_set_are_not_killed(tmp_path: Path) -> None:
    run = run_reap(PY_HOOK, "ssh-reap-stop.json", tmp_path, 6, self_pids="101,105")
    assert run.killed == []
