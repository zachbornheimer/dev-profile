"""frustration-learn.py: launches a learner on a model's frustration verdict, at most once per session per cooldown."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from hook_harness import HookRunner

HOOK = "frustration-learn.py"
SESSION_UUID = "01a16640-e539-7216-8292-baf00dd35caa"
ANGRY = "wtf, I already told you not to do that again"
JUDGED = ["--judged", "0.91"]


@pytest.fixture
def launcher(tmp_path: Path) -> tuple[Path, Path]:
    record = tmp_path / "launched.txt"
    script = tmp_path / "fake-launch"
    script.write_text(f'#!/bin/sh\necho "$@" >> {record}\n')
    script.chmod(0o755)
    return script, record


def omp_session(tmp_path: Path) -> Path:
    session = tmp_path / f"2026-10-23T00-54-51-449Z_{SESSION_UUID}.jsonl"
    session.write_text("")
    return session


def env_for(script: Path, **extra: str) -> dict[str, str]:
    return {"LEARN_LAUNCH_CMD": str(script), "LEARNER": "", **extra}


def launched(record: Path) -> list[str]:
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline and not record.exists():
        time.sleep(0.05)
    return record.read_text().splitlines() if record.exists() else []


def test_without_a_model_verdict_angry_words_launch_nothing(
    hooks: HookRunner, tmp_path: Path, launcher
) -> None:
    """The words of a prompt never decide frustration; only a judged verdict does."""
    script, record = launcher
    payload = {"prompt": ANGRY, "transcript_path": str(omp_session(tmp_path))}
    run = hooks.session(HOOK, env_for(script)).run_payload(HOOK, payload)
    assert run.exit_code == 0 and "no judged verdict" in run.log
    time.sleep(0.3)
    assert not record.exists()


def test_a_judged_verdict_launches_once_per_cooldown(
    hooks: HookRunner, tmp_path: Path, launcher
) -> None:
    script, record = launcher
    payload = {
        "prompt": "please add a test",
        "cwd": "/work",
        "transcript_path": str(omp_session(tmp_path)),
    }
    session = hooks.session(HOOK, env_for(script))
    first = session.run_payload(HOOK, payload, args=JUDGED)
    second = session.run_payload(HOOK, payload, args=JUDGED)
    assert first.exit_code == second.exit_code == 0
    assert first.stdout == "" and "launch" in first.log
    assert "within the cooldown" in second.log
    assert launched(record) == [
        f"omp:{SESSION_UUID} --reason frustration signals: judged(p=0.91)"
    ]


def test_a_session_launches_again_after_the_cooldown(
    hooks: HookRunner, tmp_path: Path, launcher
) -> None:
    """A long session gets a new learner for frustration that comes after the window."""
    script, record = launcher
    payload = {"prompt": ANGRY, "transcript_path": str(omp_session(tmp_path))}
    session = hooks.session(
        HOOK, env_for(script, FRUSTRATION_LEARN_COOLDOWN_SECONDS="1")
    )
    session.run_payload(HOOK, payload, args=JUDGED)
    assert len(launched(record)) == 1
    time.sleep(1.2)
    again = session.run_payload(HOOK, payload, args=JUDGED)
    assert "launch" in again.log and "cooldown" not in again.log
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline and len(launched(record)) < 2:
        time.sleep(0.05)
    assert len(launched(record)) == 2


def test_session_comes_from_the_payload_not_an_inherited_env(
    hooks: HookRunner, tmp_path: Path, launcher
) -> None:
    """A nested omp inherits its parent's PI_SESSION_FILE; naming the session from it launched the wrong one."""
    script, record = launcher
    stale = (
        tmp_path / "2026-01-01T00-00-00-000Z_aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee.jsonl"
    )
    stale.write_text("")
    env = env_for(script, PI_SESSION_FILE=str(stale))
    payload = {"prompt": ANGRY, "transcript_path": str(omp_session(tmp_path))}
    hooks.session(HOOK, env).run_payload(HOOK, payload, args=JUDGED)
    (line,) = launched(record)
    assert line.startswith(f"omp:{SESSION_UUID} ")


@pytest.mark.parametrize(
    ("payload", "env"),
    [
        ({"prompt": ANGRY}, {}),
        (
            {"prompt": ANGRY, "session_id": SESSION_UUID},
            {"AGENT_HOOKS_AGENT": "claude", "AGENT_HOOKS_HOST": "omp"},
        ),
    ],
    ids=["no session in the payload", "omp host never falls back to a claude session"],
)
def test_an_unnamed_session_launches_nothing(
    hooks: HookRunner, tmp_path: Path, launcher, payload: dict, env: dict
) -> None:
    script, record = launcher
    run = hooks.session(HOOK, env_for(script, **env)).run_payload(
        HOOK, payload, args=JUDGED
    )
    assert run.exit_code == 0 and "unnamed-session" in run.log
    time.sleep(0.3)
    assert not record.exists()


def test_missing_transcript_file_launches_nothing(
    hooks: HookRunner, tmp_path: Path, launcher
) -> None:
    script, record = launcher
    missing = tmp_path / f"2026-10-23T00-54-51-449Z_{SESSION_UUID}.jsonl"
    payload = {"prompt": ANGRY, "transcript_path": str(missing)}
    run = hooks.session(HOOK, env_for(script)).run_payload(HOOK, payload, args=JUDGED)
    assert run.exit_code == 0 and "unnamed-session" in run.log
    time.sleep(0.3)
    assert not record.exists()


def test_a_judged_verdict_never_launches_in_a_learner_session(
    hooks: HookRunner, tmp_path: Path, launcher
) -> None:
    script, record = launcher
    payload = {"prompt": ANGRY, "transcript_path": str(omp_session(tmp_path))}
    run = hooks.session(HOOK, env_for(script, LEARNER="1")).run_payload(
        HOOK, payload, args=JUDGED
    )
    assert run.exit_code == 0 and run.log == ""
    time.sleep(0.3)
    assert not record.exists()


def test_launch_exports_learner_and_stamp_env(
    hooks: HookRunner, tmp_path: Path
) -> None:
    record = tmp_path / "env.json"
    script = tmp_path / "fake-launch"
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, pathlib\n"
        f"pathlib.Path({str(record)!r}).write_text(json.dumps({{\n"
        "  'LEARNER': os.environ.get('LEARNER'),\n"
        "  'AGENTMUX_NESTED_RUN': os.environ.get('AGENTMUX_NESTED_RUN'),\n"
        "  'LEARN_STAMP_FILE': os.environ.get('LEARN_STAMP_FILE'),\n"
        "}))\n"
    )
    script.chmod(0o755)
    payload = {"prompt": ANGRY, "transcript_path": str(omp_session(tmp_path))}
    hooks.session(HOOK, env_for(script)).run_payload(HOOK, payload, args=JUDGED)
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline and not record.exists():
        time.sleep(0.05)
    captured = json.loads(record.read_text())
    assert captured["LEARNER"] == "1"
    assert captured["AGENTMUX_NESTED_RUN"] == "1"
    assert captured["LEARN_STAMP_FILE"] and Path(captured["LEARN_STAMP_FILE"]).is_file()
