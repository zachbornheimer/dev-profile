"""scope-guard judges a tool call against the ask just submitted, even before the transcript holds it.

omp flushes a session to its store in batches. Measured on omp:01a19d6a: the prompt
"What is 17 + 25?" was submitted at 18:00:40, an off-task write ran at 18:00:45 and was
allowed with no-user-task, and the prompt reached the store at 18:01:15.
"""

from __future__ import annotations

import json
from pathlib import Path

from hook_harness import HOOKS_DIR, HookRun, HookSession

HOOK = "scope-guard.py"
FAKE_JUDGE = HOOKS_DIR / "tests" / "fixtures" / "scope-judge" / "fake_judge.py"
# The corroborated detour: OffTopic, UnnecessaryWork, execute_proposed_call.
DETOUR_SCORES = "scores:0.94,0.96,0.03"
ASK = "What is 17 + 25? Reply with just the number."
DETOUR = "mkdir -p ~/vacation && printf 'Paris itinerary' > ~/vacation/plan.md"


def session(
    tmp_path: Path, stored: tuple[tuple[str, str], ...] = ()
) -> tuple[HookSession, Path]:
    """A session whose transcript holds the ``stored`` (prompt, timestamp) pairs."""
    lines = [{"type": "session", "id": "s1", "cwd": "/w"}]
    lines += [
        {
            "type": "message",
            "timestamp": at,
            "message": {"role": "user", "content": text},
        }
        for text, at in stored
    ]
    # Compact, as omp writes it: the reader keeps a row by a literal '"type":"message"'.
    rows = "".join(json.dumps(line, separators=(",", ":")) + "\n" for line in lines)
    transcript = tmp_path / "session.jsonl"
    transcript.write_text(rows)
    env = {"HC_SCOPE_JUDGE_CLI": str(FAKE_JUDGE), "SCOPE_JUDGE_FAKE": DETOUR_SCORES}
    return HookSession(tmp_path / "state", env), transcript


def event(name: str, transcript: Path, **fields: object) -> dict[str, object]:
    return {
        "hook_event_name": name,
        "session_id": "s1",
        "transcript_path": str(transcript),
        **fields,
    }


def submit(hooks: HookSession, transcript: Path, prompt: str, at: str) -> HookRun:
    return hooks.run_payload(
        HOOK,
        event("UserPromptSubmit", transcript, prompt=prompt),
        env={"HC_NOW_ISO_OVERRIDE": at},
    )


def detour(hooks: HookSession, transcript: Path) -> HookRun:
    return hooks.run_payload(
        HOOK,
        event(
            "PreToolUse",
            transcript,
            tool_name="mcp__capability_agentmux_capability_run_command",
            tool_input={"command": DETOUR},
        ),
    )


def reason(run: HookRun) -> str:
    return run.output["hookSpecificOutput"]["permissionDecisionReason"]


def test_an_off_task_call_is_denied_against_the_ask_the_transcript_does_not_hold_yet(
    tmp_path: Path,
) -> None:
    hooks, transcript = session(tmp_path)
    submitted = submit(hooks, transcript, ASK, "2026-11-02T18:00:40Z")
    assert (submitted.exit_code, submitted.decision) == (0, "none")

    call = detour(hooks, transcript)
    assert call.decision == "deny"
    assert ASK in reason(call)


def test_an_ask_the_transcript_stores_in_another_form_does_not_become_the_current_task(
    tmp_path: Path,
) -> None:
    current = "Now run the login test under CI"
    hooks, transcript = session(
        tmp_path,
        stored=(
            ("Skill fix-flaky: repair the login test", "2026-11-02T18:00:40.512Z"),
            (current, "2026-11-02T18:05:00.100Z"),
        ),
    )
    submit(hooks, transcript, "/fix-flaky login", "2026-11-02T18:00:40Z")
    submit(hooks, transcript, current, "2026-11-02T18:05:00Z")

    call = detour(hooks, transcript)
    assert call.decision == "deny"
    assert current in reason(call)
    assert "/fix-flaky login" not in reason(call)


def test_without_a_submitted_ask_or_a_stored_one_the_call_is_not_judged(
    tmp_path: Path,
) -> None:
    hooks, transcript = session(tmp_path)
    call = detour(hooks, transcript)
    assert call.decision == "none"
    assert "no-user-task" in call.log
