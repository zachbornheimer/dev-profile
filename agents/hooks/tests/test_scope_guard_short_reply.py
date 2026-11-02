"""scope-guard judges a short reply together with the agent question it answers.

Measured on omp 01a19986 (2026-11-02 ~19:37Z): the agent asked ``gh repo create
... && git push?  Reply "yes" or "no".'' and the user replied ``yes``; the guard
judged the task as the last three asks alone — ending in ``yes`` — and denied
the approved ``gh repo create`` as off-task-and-unnecessary. The agent question
was in the transcript the whole time.

Rule (one line): only a reply under SHORT_REPLY_CHARS is re-labeled with the
agent message it answers; a long self-contained ask never gains one, so the
rule cannot make a long ask worse.
"""

from __future__ import annotations

import json
from pathlib import Path

from hook_harness import HOOKS_DIR, HookRun, HookSession

HOOK = "scope-guard.py"
FAKE_JUDGE = HOOKS_DIR / "tests" / "fixtures" / "scope-judge" / "fake_judge.py"
# The corroborated detour: OffTopic, UnnecessaryWork, execute_proposed_call.
DETOUR_SCORES = "scores:0.94,0.96,0.03"
AGENT_QUESTION = (
    "Should I create a private GitHub repo for agent-hooks and push it?\n"
    'Reply "yes" or "no".'
)
# The judged task carries the agent message trimmed to its final question.
FINAL_QUESTION = "Should I create a private GitHub repo for agent-hooks and push it?"
APPROVED_PUSH = (
    "gh repo create zachbornheimer/agent-hooks --private --source . "
    "--remote origin && git push -u origin main"
)
OLDER_ASK = "Please keep the hook suites green while you work."
LONG_ASK = (
    "Add a unit test for the cache module covering eviction and reload, "
    "then run the suite twice and paste the tail."
)
# LONG_ASK stays long: the short-reply rule must never reach a self-contained ask.
assert len(LONG_ASK) >= 80


def session(tmp_path: Path) -> tuple[HookSession, Path]:
    """A session whose judge denies the corroborated detour shape."""
    env = {"HC_SCOPE_JUDGE_CLI": str(FAKE_JUDGE), "SCOPE_JUDGE_FAKE": DETOUR_SCORES}
    return HookSession(tmp_path / "state", env), tmp_path / "session.jsonl"


def write_transcript(
    path: Path,
    asks: tuple[tuple[str, str], ...],
    agent_replies: tuple[str, ...] = (),
) -> Path:
    """An omp session log: one reply row after each ask but the last.

    Compact, as omp writes it: the reader keeps a row by a literal
    ``'"type":"message"'``.
    """
    rows = [{"type": "session", "id": "s1", "cwd": "/w"}]
    for index, (text, at) in enumerate(asks):
        rows.append(
            {
                "type": "message",
                "timestamp": at,
                "message": {"role": "user", "content": text, "attribution": "user"},
            }
        )
        if index < len(agent_replies):
            rows.append(
                {
                    "type": "message",
                    "timestamp": at,
                    "message": {
                        "role": "assistant",
                        "content": [{"type": "text", "text": agent_replies[index]}],
                    },
                }
            )
    body = "".join(json.dumps(row, separators=(",", ":")) + "\n" for row in rows)
    path.write_text(body)
    return path


def push(hooks: HookSession, transcript: Path) -> HookRun:
    """The approved pre-push call, as the guard intercepts it."""
    return hooks.run_payload(
        HOOK,
        {
            "hook_event_name": "PreToolUse",
            "session_id": "s1",
            "transcript_path": str(transcript),
            "tool_name": "mcp__capability_agentmux_capability_run_command",
            "tool_input": {"command": APPROVED_PUSH},
        },
    )


def reason(run: HookRun) -> str:
    return run.output["hookSpecificOutput"]["permissionDecisionReason"]


def test_a_short_yes_is_judged_with_the_agent_question_it_answers(
    tmp_path: Path,
) -> None:
    """Red on main: the agent asked, the user answered, the answer was ``yes``."""
    hooks, transcript = session(tmp_path)
    write_transcript(
        transcript,
        (
            (OLDER_ASK, "2026-11-02T19:30:00Z"),
            ("yes", "2026-11-02T19:37:00Z"),
        ),
        (AGENT_QUESTION,),
    )

    call = push(hooks, transcript)
    assert call.decision == "deny"
    assert FINAL_QUESTION in reason(call)
    assert "Agent asked:" in reason(call)
    assert "User replied: yes" in reason(call)


def test_b_a_long_self_contained_ask_gains_no_agent_message(
    tmp_path: Path,
) -> None:
    """A long ask already names its work, so it is never paired with the agent's."""
    hooks, transcript = session(tmp_path)
    write_transcript(
        transcript,
        (
            (OLDER_ASK, "2026-11-02T19:30:00Z"),
            (LONG_ASK, "2026-11-02T19:37:00Z"),
        ),
        (AGENT_QUESTION,),
    )

    call = push(hooks, transcript)
    assert call.decision == "deny"
    assert "Agent asked:" not in reason(call)
    assert AGENT_QUESTION not in reason(call)
    assert LONG_ASK in reason(call)


def test_c_without_an_agent_message_the_task_is_unchanged(
    tmp_path: Path,
) -> None:
    """No agent reply row: the task stays the asks alone, as before."""
    hooks, transcript = session(tmp_path)
    write_transcript(
        transcript,
        (
            (OLDER_ASK, "2026-11-02T19:30:00Z"),
            ("yes", "2026-11-02T19:37:00Z"),
        ),
        (),
    )

    call = push(hooks, transcript)
    assert call.decision == "deny"
    assert "Agent asked:" not in reason(call)
    assert "User replied:" not in reason(call)
    assert "yes" in reason(call)


def test_d_a_recorded_reply_is_judged_with_the_transcript_s_last_agent_message(
    tmp_path: Path,
) -> None:
    """omp flushes in batches: the reply reaches the asks log before the transcript.

    The transcript ends mid-turn, on the agent's question; the recorded ask is
    the reply to it. The question the reply answers is the transcript's
    current-turn reply, not a completed turn's.
    """
    hooks, transcript = session(tmp_path)
    write_transcript(
        transcript,
        ((OLDER_ASK, "2026-11-02T19:30:00Z"),),
        (AGENT_QUESTION,),
    )
    submitted = hooks.run_payload(
        HOOK,
        {
            "hook_event_name": "UserPromptSubmit",
            "session_id": "s1",
            "transcript_path": str(transcript),
            "prompt": "yes",
        },
        env={"HC_NOW_ISO_OVERRIDE": "2026-11-02T19:37:00Z"},
    )
    assert (submitted.exit_code, submitted.decision) == (0, "none")

    call = push(hooks, transcript)
    assert call.decision == "deny"
    assert FINAL_QUESTION in reason(call)
    assert "Agent asked:" in reason(call)
    assert "User replied: yes" in reason(call)
