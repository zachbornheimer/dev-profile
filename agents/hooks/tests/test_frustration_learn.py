"""frustration-learn.py: launches a learner at most once per session per cooldown, only on real signals."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest
from hook_harness import HOOKS_DIR, HookRunner

sys.path.insert(0, str(HOOKS_DIR / "lib"))
from frustration import THRESHOLD, score, transcript_signals

HOOK = "frustration-learn.py"
SESSION_UUID = "01a16640-e539-7216-8292-baf00dd35caa"
ANGRY = "wtf, I already told you not to do that again"
CALM = "Please add a test for the retry path."


def omp_user(text: str) -> dict:
    return {
        "type": "message",
        "message": {"role": "user", "content": [{"type": "text", "text": text}]},
    }


def omp_result(is_error: bool) -> dict:
    return {
        "type": "message",
        "message": {"role": "toolResult", "isError": is_error, "content": []},
    }


def claude_result(is_error: bool) -> dict:
    part = {
        "type": "tool_result",
        "tool_use_id": "t",
        "content": "x",
        "is_error": is_error,
    }
    return {"type": "user", "message": {"role": "user", "content": [part]}}


def write_jsonl(path: Path, entries: list[dict]) -> Path:
    path.write_text("\n".join(json.dumps(e) for e in entries) + "\n")
    return path


@pytest.mark.parametrize(
    ("prompt", "triggered"),
    [
        (CALM, False),
        ("try it again", False),  # one mild phrase stays under the threshold
        ("wtf", True),
        (ANGRY, True),
        ("WHY IS THIS STILL BROKEN, FIX IT NOW", True),
        # Real prompts from the replay of 477 sessions: corrections of the agent launch alone.
        ("HOW MANY TIMES DO I HAVE TO SAY RUN IT THRU MASTRA", True),
        ("i told you what to do, use what i said - typesafe thru openrouter", True),
        (
            "that's not what i asked. I want to know what happened when the agent was running",
            True,
        ),
        ("why aren't you fully completing the task? what's causing you to stop", True),
        ("why aren't you using worktrunk", True),
        (
            "do you have a web search tool?",
            False,
        ),  # a question about capability, not a correction
        # Ordinary prompts the first version launched on.
        ("how do we make this idiot proof? the automatic waiting seems wrong", False),
        ("as I said earlier, the retry path needs a test", False),
        ("stop it. Talk to me about how the claiming process works please.", False),
        (("wtf " + "context " * 400), False),  # long prompt = pasted or injected text
        (
            "<task-notification> wtf I already told you again </task-notification>",
            False,
        ),
        ("[Request interrupted by user for tool use]", False),
    ],
)
def test_score_threshold(prompt: str, triggered: bool) -> None:
    assert score(prompt).triggered is triggered


def test_threshold_is_reachable_only_by_combining_weak_signals() -> None:
    assert score("seriously, again??").total >= THRESHOLD


def test_tool_errors_and_a_repeat_corroborate_but_never_launch_alone() -> None:
    ask = "is there a way we can self host it without adding a server to manage"
    assert not score(ask, [ask], recent_tool_errors=10).triggered


def test_injected_user_text_is_not_an_earlier_prompt(tmp_path: Path) -> None:
    notice = "<task-notification> <task-id>b1</task-id> background task finished with output </task-notification>"
    path = write_jsonl(tmp_path / "s.jsonl", [omp_user(notice), omp_user(CALM)])
    assert transcript_signals(path, "x")[0] == [CALM]


def test_repeated_request_counts_but_a_prompt_never_matches_itself(
    tmp_path: Path,
) -> None:
    ask = "rename the config loader so it reads from the new settings file"
    path = write_jsonl(
        tmp_path / "s.jsonl", [omp_user(ask), omp_user(CALM), omp_user(ask)]
    )
    prior, _ = transcript_signals(path, ask)
    assert prior == [
        ask,
        CALM,
    ]  # newest copy of the current prompt is dropped, the older kept
    assert "repeated-request" in score(ask, prior).reasons
    assert "repeated-request" not in score(ask, [CALM]).reasons


@pytest.mark.parametrize("result", [omp_result, claude_result])
def test_tool_error_window_counts_errors_in_both_transcript_shapes(
    tmp_path: Path, result
) -> None:
    path = write_jsonl(
        tmp_path / "s.jsonl", [result(True)] * 3 + [result(False)] + [result(True)] * 2
    )
    assert transcript_signals(path, "x")[1] == 5


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


def test_frustrated_prompt_launches_once_per_cooldown(
    hooks: HookRunner, tmp_path: Path, launcher
) -> None:
    script, record = launcher
    payload = {
        "prompt": ANGRY,
        "cwd": "/work",
        "transcript_path": str(omp_session(tmp_path)),
    }
    session = hooks.session(HOOK, env_for(script))
    first = session.run_payload(HOOK, payload)
    second = session.run_payload(HOOK, payload)
    assert first.exit_code == second.exit_code == 0
    assert first.stdout == "" and "launch" in first.log
    assert "within the cooldown" in second.log
    lines = launched(record)
    assert len(lines) == 1
    assert lines[0].startswith(f"omp:{SESSION_UUID} --reason frustration signals:")


def test_a_session_launches_again_after_the_cooldown(
    hooks: HookRunner, tmp_path: Path, launcher
) -> None:
    """A long session gets a new learner for frustration that comes after the window."""
    script, record = launcher
    payload = {"prompt": ANGRY, "transcript_path": str(omp_session(tmp_path))}
    session = hooks.session(
        HOOK, env_for(script, FRUSTRATION_LEARN_COOLDOWN_SECONDS="1")
    )
    session.run_payload(HOOK, payload)
    assert len(launched(record)) == 1
    time.sleep(1.2)
    again = session.run_payload(HOOK, payload)
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
    hooks.session(HOOK, env).run_payload(HOOK, payload)
    (line,) = launched(record)
    assert line.startswith(f"omp:{SESSION_UUID} ")


def test_payload_without_a_session_launches_nothing(
    hooks: HookRunner, tmp_path: Path, launcher
) -> None:
    script, record = launcher
    run = hooks.session(HOOK, env_for(script)).run_payload(HOOK, {"prompt": ANGRY})
    assert run.exit_code == 0 and "unnamed-session" in run.log
    time.sleep(0.3)
    assert not record.exists()


def test_calm_prompt_launches_nothing(
    hooks: HookRunner, tmp_path: Path, launcher
) -> None:
    script, record = launcher
    payload = {"prompt": CALM, "transcript_path": str(omp_session(tmp_path))}
    run = hooks.session(HOOK, env_for(script)).run_payload(HOOK, payload)
    assert run.exit_code == 0 and run.log == ""
    time.sleep(0.3)
    assert not record.exists()


def test_a_learner_session_never_launches_a_learner(
    hooks: HookRunner, tmp_path: Path, launcher
) -> None:
    script, record = launcher
    payload = {"prompt": ANGRY, "transcript_path": str(omp_session(tmp_path))}
    run = hooks.session(HOOK, env_for(script, LEARNER="1")).run_payload(HOOK, payload)
    assert run.exit_code == 0 and run.log == ""
    time.sleep(0.3)
    assert not record.exists()


def test_a_judged_verdict_launches_where_the_lexical_score_does_not(
    hooks: HookRunner, tmp_path: Path, launcher
) -> None:
    """detect_frustration's yes launches even when the words carry no lexical signal."""
    script, record = launcher
    payload = {"prompt": CALM, "transcript_path": str(omp_session(tmp_path))}
    run = hooks.session(HOOK, env_for(script)).run_payload(
        HOOK, payload, args=["--judged", "0.91"]
    )
    assert run.exit_code == 0 and "launch" in run.log
    (line,) = launched(record)
    assert line == f"omp:{SESSION_UUID} --reason frustration signals: judged(p=0.91)"


def test_one_launch_per_cooldown_across_the_lexical_and_judged_paths(
    hooks: HookRunner, tmp_path: Path, launcher
) -> None:
    """Both hooks see the same angry prompt; the session still gets one learner."""
    script, record = launcher
    payload = {"prompt": ANGRY, "transcript_path": str(omp_session(tmp_path))}
    session = hooks.session(HOOK, env_for(script))
    session.run_payload(HOOK, payload)
    judged = session.run_payload(HOOK, payload, args=["--judged", "0.95"])
    assert "within the cooldown" in judged.log
    time.sleep(0.3)
    assert len(launched(record)) == 1


def test_a_judged_verdict_never_launches_in_a_learner_session(
    hooks: HookRunner, tmp_path: Path, launcher
) -> None:
    script, record = launcher
    payload = {"prompt": ANGRY, "transcript_path": str(omp_session(tmp_path))}
    run = hooks.session(HOOK, env_for(script, LEARNER="1")).run_payload(
        HOOK, payload, args=["--judged", "0.95"]
    )
    assert run.exit_code == 0 and run.log == ""
    time.sleep(0.3)
    assert not record.exists()


def test_omp_host_without_transcript_never_falls_back_to_claude_session(
    hooks: HookRunner, tmp_path: Path, launcher
) -> None:
    script, record = launcher
    env = env_for(script, AGENT_HOOKS_AGENT="claude", AGENT_HOOKS_HOST="omp")
    payload = {"prompt": ANGRY, "session_id": SESSION_UUID}
    run = hooks.session(HOOK, env).run_payload(HOOK, payload)
    assert run.exit_code == 0 and "unnamed-session" in run.log
    time.sleep(0.3)
    assert not record.exists()


def test_missing_transcript_file_launches_nothing(
    hooks: HookRunner, tmp_path: Path, launcher
) -> None:
    script, record = launcher
    missing = tmp_path / f"2026-10-23T00-54-51-449Z_{SESSION_UUID}.jsonl"
    payload = {"prompt": ANGRY, "transcript_path": str(missing)}
    run = hooks.session(HOOK, env_for(script)).run_payload(HOOK, payload)
    assert run.exit_code == 0 and "unnamed-session" in run.log
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
    hooks.session(HOOK, env_for(script)).run_payload(HOOK, payload)
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline and not record.exists():
        time.sleep(0.05)
    captured = json.loads(record.read_text())
    assert captured["LEARNER"] == "1"
    assert captured["AGENTMUX_NESTED_RUN"] == "1"
    assert captured["LEARN_STAMP_FILE"] and Path(captured["LEARN_STAMP_FILE"]).is_file()
