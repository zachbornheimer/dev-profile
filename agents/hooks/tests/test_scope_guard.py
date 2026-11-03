"""scope-guard.py: the bars, the deterministic refusals, and the fail-opens.

Every test drives the real hook by path with a fake judge (``HC_SCOPE_JUDGE_CLI``) and
asserts the two consumer-visible outputs of each event: the hook's JSON decision and the
``scope-judgments.jsonl`` line the hook appends. The fake judge takes one score per
question, in the order the guard asks them — a tool call asks OffTopic, UnnecessaryWork,
execute_proposed_call; a Stop asks OffTopic, UnnecessaryWork — and the deny-side numbers
replay the live traffic that set the bars (2026-10-30,
``~/.agents/hooks/state/scope-judgments.jsonl``): the ``pkill -f node; ps aux --sort=-%cpu``
detour scored 0.94 / 0.96 / 0.03 against "push the current branch", while a benign
``git commit -S`` scored higher still — which is why a single strong signal alone never
denies a call. The policy's constants live in ``lib/scope_guard_rules.py``; these tests
pin their behavior at the boundaries, on the paths above them:

  tool.before -> deny when OffTopic >= 0.80 AND UnnecessaryWork >= 0.75, or
                 UnnecessaryWork >= 0.88, unless execute_proposed_call > 0.35;
  turn.stop   -> block when OffTopic >= 0.88 AND UnnecessaryWork >= 0.80;
  read-only probes, the `mise run ci` prohibition, the repeat-call ledger, and the
  correction cap are decided without the judge; everything the guard cannot judge
  fails open, with the reason in the log line.

Transcripts are written into the test's state dir under non-omp file names, so
``omp_session_store`` never consults the session database from these tests.
"""

from __future__ import annotations

import json

import pytest
from hook_harness import FIXTURES_DIR, HookRun, HookSession

PY_HOOK = "scope-guard.py"
STEM = "scope-guard"
JUDGMENTS_LOG = "scope-judgments.jsonl"
FAKE_JUDGE = FIXTURES_DIR / "scope-judge" / "fake_judge.py"
TASK = "push the current branch to origin, then tell me the SHA"
# The detour this guard exists for, at the score real traffic gave it.
HOST_DRIFT = "pkill -f node; ps aux --sort=-%cpu | head -20"
ON_TASK = "git push origin HEAD"
PROBE = "wt switch --help"
# `--help` on a command that still writes: the probe skip must not swallow it.
PROBE_THAT_WRITES = "omp --help > /tmp/scope-guard-help.txt"
CI_COMMAND = "mise run ci"
CI_PROHIBITED_TASK = "ship the fix, but do not run mise run ci"
CI_AUTHORIZED_TASK = "the pins are bumped; please run mise run ci"
CI_UNRELATED_LATER_TASK = "also tell me the SHA of the last commit"
# A turn that ends by finishing work nobody asked for.
STOPPING_EARLY = (
    "I finished the pin bump. While waiting I also refactored my dotfiles, "
    "rebuilt my prompt theme, and cleaned up my Downloads folder."
)
# Scores, one per question in the order the guard asks them.
DRIFT = "scores:0.94,0.96,0.03"  # the corroborated detour: denied on both rules
ON_TASK_SCORES = "scores:0.04,0.05,0.90"  # execute_proposed_call > 0.35: allow
OFF_TOPIC_ALONE = "scores:0.97,0.60,0.02"  # one strong signal: allow
UNNECESSARY_ALONE = "scores:0.10,0.96,0.02"  # UnnecessaryWork >= 0.88: deny
TOOL_EDGE = "scores:0.80,0.75,0.35"  # inclusive bars, execute at its cap: deny
STOP_BLOCK = "scores:0.95,0.92"  # both Stop bars cleared: block
STOP_EDGE = "scores:0.88,0.80"  # the Stop bars are inclusive: block
STOP_ALLOW = "scores:0.87,0.92"  # OffTopic under 0.88: allow
# Before the harness's pinned now (2000-01-01T00:00:00Z), so a correction recorded this
# run falls inside the current request's window when the cap filters by its timestamp.
PROMPT_AT = "1999-12-31T00:00:00Z"
# A newer ask, past the harness's pinned now (2000-01-01T00:00:00Z): it opens a
# fresh request window, so denials recorded this run fall outside it.
LATER_PROMPT_AT = "2000-01-02T00:00:00Z"


@pytest.fixture
def state(hooks) -> HookSession:
    return hooks.session(STEM)


def rows(state: HookSession) -> list[dict]:
    """Every judgment log line the hook has appended so far."""
    path = state.state_dir / JUDGMENTS_LOG
    return (
        [json.loads(line) for line in path.read_text().splitlines()]
        if path.exists()
        else []
    )


def judge_env(mode: str, state: HookSession, **extra: str) -> dict[str, str]:
    """The fake judge, plus the file it appends every request to."""
    return {
        "HC_SCOPE_JUDGE_CLI": str(FAKE_JUDGE),
        "SCOPE_JUDGE_FAKE": mode,
        "SCOPE_JUDGE_CALLS": str(state.state_dir / "judge-calls.jsonl"),
        **extra,
    }


def asked(state: HookSession) -> list[dict]:
    """Every request the guard actually sent to the judge."""
    path = state.state_dir / "judge-calls.jsonl"
    return (
        [json.loads(line) for line in path.read_text().splitlines()]
        if path.exists()
        else []
    )


def transcript(
    state: HookSession,
    tasks: list[str] | None = None,
    name: str = "t",
    attribution: str | None = None,
    prompt_at: str = PROMPT_AT,
) -> str:
    """An omp session log: a session header, the user's turns, and one tool call.

    ``attribution="agent"`` writes what omp records for a message the harness delivered —
    the work order a parent agent delegated, which is a delegated agent's own task.
    The file name carries no omp session id, so the session database is never consulted.
    """
    if tasks is None:
        tasks = [TASK]
    lines = [json.dumps({"type": "session", "id": "s1"}, separators=(",", ":"))]
    for task in tasks:
        message = {"role": "user", "content": task}
        if attribution is not None:
            message["attribution"] = attribution
        lines.append(
            json.dumps(
                {"type": "message", "timestamp": prompt_at, "message": message},
                separators=(",", ":"),
            )
        )
        lines.append(
            json.dumps(
                {
                    "type": "message",
                    "timestamp": prompt_at,
                    "message": {
                        "role": "assistant",
                        "content": [
                            {"type": "text", "text": "On it."},
                            {
                                "type": "toolCall",
                                "id": "c1",
                                "name": "bash",
                                "arguments": {"command": "git status --short"},
                            },
                        ],
                    },
                },
                separators=(",", ":"),
            )
        )
        lines.append(
            json.dumps(
                {
                    "type": "message",
                    "timestamp": prompt_at,
                    "message": {
                        "role": "toolResult",
                        "toolCallId": "c1",
                        "content": " M a.py",
                        "isError": False,
                    },
                },
                separators=(",", ":"),
            )
        )
    path = state.state_dir / f"{name}.jsonl"
    path.write_text("\n".join(lines) + "\n")
    return str(path)


def tool_payload(
    tpath: str, command: str, tool: str = "Bash", **input_extra: str
) -> dict:
    return {
        "session_id": "s-scope",
        "transcript_path": tpath,
        "cwd": "/tmp",
        "hook_event_name": "PreToolUse",
        "tool_name": tool,
        "tool_input": {"command": command, **input_extra},
    }


def stop_payload(tpath: str, message: str, **extra: object) -> dict:
    return {
        "session_id": "s-scope",
        "transcript_path": tpath,
        "cwd": "/tmp",
        "hook_event_name": "Stop",
        "last_assistant_message": message,
        **extra,
    }


def run(state: HookSession, payload: dict, mode: str = DRIFT, **env: str) -> HookRun:
    return state.run_payload(PY_HOOK, payload, judge_env(mode, state, **env))


def reason_of(run_result: HookRun) -> str:
    output = run_result.output or {}
    specific = output.get("hookSpecificOutput") or {}
    return specific.get("permissionDecisionReason") or output.get("reason") or ""


# --- 1. a tool call: corroboration, execute support, and the edges -------------------


def test_an_off_task_call_is_denied_with_the_task_and_the_rejected_call(
    state: HookSession,
) -> None:
    result = run(state, tool_payload(transcript(state), HOST_DRIFT))
    assert result.decision == "deny", result.output
    reason = reason_of(result)
    assert TASK in reason
    assert HOST_DRIFT in reason
    assert "Reason: off-task-and-unnecessary." in reason
    assert "Return to the user's request" in reason
    row = rows(state)[-1]
    assert row["decision"] == "off-task-tool-call"
    assert row["decision_kind"] == "deny"
    assert row["source"] == "model"
    assert row["scores"] == {
        "OffTopic": 0.94,
        "UnnecessaryWork": 0.96,
        "execute_proposed_call": 0.03,
    }
    assert row["hop"] == "typesafe"
    assert row["task"] == TASK
    assert row["candidate"] == f"Bash: {HOST_DRIFT}"
    request = asked(state)[0]
    assert request["context"]["user_request"] == TASK
    assert request["context"]["candidate_event"] == {
        "kind": "tool",
        "content": f"Bash: {HOST_DRIFT}",
    }
    assert len(request["questions"]) == 3


def test_an_execute_supported_call_is_allowed_above_the_veto_bar(
    state: HookSession,
) -> None:
    """Model support wins outright: execute_proposed_call > 0.35 vetoes the veto."""
    result = run(state, tool_payload(transcript(state), ON_TASK), mode=ON_TASK_SCORES)
    assert result.decision == "none", result.output
    assert asked(state) != []
    row = rows(state)[-1]
    assert row["decision"] == "allow"
    assert row["reason"] == ""
    assert row["scores"]["execute_proposed_call"] == 0.90


def test_execute_support_at_exactly_the_bar_does_not_win(state: HookSession) -> None:
    """0.35 is not > 0.35, so the corroborated waste signals still decide."""
    result = run(state, tool_payload(transcript(state), HOST_DRIFT), mode=TOOL_EDGE)
    assert result.decision == "deny", result.output
    assert "Reason: off-task-and-unnecessary." in reason_of(result)
    row = rows(state)[-1]
    assert row["decision"] == "off-task-tool-call"
    assert row["scores"]["execute_proposed_call"] == 0.35
    assert row["scores"]["OffTopic"] == 0.80
    assert row["scores"]["UnnecessaryWork"] == 0.75


def test_one_strong_signal_alone_allows(state: HookSession) -> None:
    """Corroboration: a lone off-topic score under UnnecessaryWork 0.75 never denies."""
    result = run(
        state, tool_payload(transcript(state), HOST_DRIFT), mode=OFF_TOPIC_ALONE
    )
    assert result.decision == "none", result.output
    row = rows(state)[-1]
    assert row["decision"] == "allow"
    assert row["reason"] == ""
    assert row["scores"]["OffTopic"] == 0.97


def test_clearly_unnecessary_work_alone_denies(state: HookSession) -> None:
    """The one single signal that denies on its own: UnnecessaryWork >= 0.88."""
    result = run(
        state, tool_payload(transcript(state), HOST_DRIFT), mode=UNNECESSARY_ALONE
    )
    assert result.decision == "deny", result.output
    assert "Reason: clearly-unnecessary." in reason_of(result)
    row = rows(state)[-1]
    assert row["decision"] == "off-task-tool-call"
    assert row["scores"]["UnnecessaryWork"] == 0.96


def test_an_on_task_call_passes_untouched(state: HookSession) -> None:
    """Everything scored low: allowed, judged, and the log says so."""
    result = run(
        state, tool_payload(transcript(state), ON_TASK), mode="scores:0.02,0.03,0.05"
    )
    assert result.decision == "none", result.output
    row = rows(state)[-1]
    assert row["decision"] == "allow"
    assert row["reason"] == ""


# --- 2. the Stop side: a stronger bar, because a wrong block only delays --------------


def test_a_turn_that_ends_off_task_is_blocked(state: HookSession) -> None:
    result = run(
        state, stop_payload(transcript(state), STOPPING_EARLY), mode=STOP_BLOCK
    )
    assert result.decision == "block", result.output
    reason = reason_of(result)
    assert TASK in reason
    assert "Reason: off-task-ending." in reason
    assert "Finish the requested work" in reason
    row = rows(state)[-1]
    assert row["decision"] == "off-task-turn-end"
    assert row["decision_kind"] == "block"
    assert row["scores"] == {"OffTopic": 0.95, "UnnecessaryWork": 0.92}
    assert row["candidate"] == STOPPING_EARLY
    request = asked(state)[0]
    assert request["context"]["candidate_event"] == {
        "kind": "conversation",
        "content": STOPPING_EARLY,
    }
    assert len(request["questions"]) == 2


def test_the_stop_bar_is_inclusive_at_its_edge(state: HookSession) -> None:
    result = run(state, stop_payload(transcript(state), STOPPING_EARLY), mode=STOP_EDGE)
    assert result.decision == "block", result.output
    assert "Reason: off-task-ending." in reason_of(result)
    assert rows(state)[-1]["decision"] == "off-task-turn-end"


def test_a_stop_under_the_off_topic_bar_allows(state: HookSession) -> None:
    """Even a clearly unnecessary ending needs OffTopic >= 0.88 to block."""
    result = run(
        state, stop_payload(transcript(state), STOPPING_EARLY), mode=STOP_ALLOW
    )
    assert result.decision == "none", result.output
    row = rows(state)[-1]
    assert row["decision"] == "allow"
    assert row["reason"] == ""
    assert row["scores"] == {"OffTopic": 0.87, "UnnecessaryWork": 0.92}


# --- 3. decided without the judge: probes and explicit prohibitions -------------------


def test_a_read_only_probe_is_allowed_without_the_judge(state: HookSession) -> None:
    result = run(state, tool_payload(transcript(state), PROBE))
    assert result.decision == "none", result.output
    assert asked(state) == []
    row = rows(state)[-1]
    assert row["decision"] == "allow"
    assert row["reason"] == "read-only-probe"
    assert row["scores"] == {}


def test_a_probe_shape_that_writes_still_reaches_the_judge(state: HookSession) -> None:
    """`--help` with a redirect acts on the host, so the skip must not swallow it."""
    result = run(state, tool_payload(transcript(state), PROBE_THAT_WRITES))
    assert asked(state) != []
    assert result.decision == "deny", result.output


@pytest.mark.parametrize(
    "tool",
    ["read", "mcp__capability_agentmux_capability_grep"],
    ids=["omp-read", "gateway-grep"],
)
def test_a_read_only_tool_is_allowed_without_the_judge(
    state: HookSession, tool: str
) -> None:
    """omp's read and the gateway's grep only look, so they never cost a judge call."""
    payload = tool_payload(
        transcript(state),
        "",
        tool=tool,
        file_path="/tmp/session.jsonl",
        pattern="scope",
    )
    result = run(state, payload)
    assert result.decision == "none", result.output
    assert asked(state) == []
    row = rows(state)[-1]
    assert row["decision"] == "allow"
    assert row["reason"] == "read-only-tool"
    assert row["scores"] == {}


def test_an_edit_and_a_mutating_shell_call_are_still_judged(
    state: HookSession,
) -> None:
    """The skip is for tools that only look; a file edit and a Bash call still pay."""
    edit = run(
        state,
        tool_payload(
            transcript(state),
            "",
            tool="edit",
            file_path="/tmp/a.py",
            old_string="x",
            new_string="y",
        ),
    )
    assert edit.decision == "deny", edit.output
    bash = run(state, tool_payload(transcript(state, name="t2"), HOST_DRIFT))
    assert bash.decision == "deny", bash.output
    assert len(asked(state)) == 2
    assert rows(state)[-1]["decision"] == "off-task-tool-call"
    """`--help` with a redirect acts on the host, so the skip must not swallow it."""
    result = run(state, tool_payload(transcript(state), PROBE_THAT_WRITES))
    assert asked(state) != []
    assert result.decision == "deny", result.output


def test_a_prohibited_full_ci_call_is_denied_without_the_judge(
    state: HookSession,
) -> None:
    tpath = transcript(state, [CI_PROHIBITED_TASK])
    result = run(state, tool_payload(tpath, CI_COMMAND))
    assert result.decision == "deny", result.output
    assert asked(state) == []
    reason = reason_of(result)
    assert "User explicitly prohibited `mise run ci`." in reason
    assert CI_PROHIBITED_TASK in reason
    row = rows(state)[-1]
    assert row["decision"] == "off-task-tool-call"
    assert row["source"] == "explicit-constraint"
    assert row["scores"] == {}


def test_a_later_authorization_runs_the_ci(state: HookSession) -> None:
    """The prohibition honors the latest explicit instruction, so this is judged."""
    tpath = transcript(state, [CI_PROHIBITED_TASK, CI_AUTHORIZED_TASK])
    result = run(state, tool_payload(tpath, CI_COMMAND), mode=ON_TASK_SCORES)
    assert result.decision == "none", result.output
    assert asked(state) != []
    row = rows(state)[-1]
    assert row["decision"] == "allow"
    assert row["reason"] == ""


def test_an_unrelated_later_prompt_keeps_the_prohibition(state: HookSession) -> None:
    tpath = transcript(state, [CI_PROHIBITED_TASK, CI_UNRELATED_LATER_TASK])
    result = run(state, tool_payload(tpath, CI_COMMAND))
    assert result.decision == "deny", result.output
    assert asked(state) == []
    assert "User explicitly prohibited `mise run ci`." in reason_of(result)


def test_a_delegated_work_order_is_still_the_task(state: HookSession) -> None:
    """omp attributes a parent agent's work order to "agent"; it is still the task."""
    tpath = transcript(state, attribution="agent")
    result = run(state, tool_payload(tpath, HOST_DRIFT))
    assert result.decision == "deny", result.output
    assert TASK in reason_of(result)
    assert rows(state)[-1]["task"] == TASK


# --- 4. the repeat-call ledger and the correction cap --------------------------------


def test_the_same_denied_call_is_denied_again_without_a_second_judgment(
    state: HookSession,
) -> None:
    payload = tool_payload(transcript(state), HOST_DRIFT)
    assert run(state, payload).decision == "deny"
    second = run(state, payload)
    assert second.decision == "deny", second.output
    assert len(asked(state)) == 1
    reason = reason_of(second)
    assert "This exact tool call was already denied for this request." in reason
    assert HOST_DRIFT in reason
    row = rows(state)[-1]
    assert row["decision"] == "off-task-tool-call"
    assert row["source"] == "explicit-constraint"
    assert row["scores"] == {}


def test_a_denied_call_refusal_forbids_the_retry(state: HookSession) -> None:
    """A refusal the agent can act on: no retry, and the user can authorize."""
    result = run(state, tool_payload(transcript(state), HOST_DRIFT))
    reason = reason_of(result)
    assert "Do not retry this call" in reason
    assert "ask the user to authorize it explicitly" in reason
    # The first denial of a request carries no count.
    assert "This is denial" not in reason


def test_a_rephrased_retry_names_its_denial_number(state: HookSession) -> None:
    """A second, rephrased attempt is denied again and says it is the second.

    The exact-repeat ledger cannot catch it (the text differs), so the refusal
    itself must close the loop: measured on omp 01a188f, one landing call was
    refused four more times, a judge call each, because the refusal never said
    the retry was futile.
    """
    assert run(state, tool_payload(transcript(state), HOST_DRIFT)).decision == "deny"
    rephrased = "ps aux --sort=-%cpu | head -20; pkill -f node"
    second = run(state, tool_payload(transcript(state, name="t2"), rephrased))
    assert second.decision == "deny", second.output
    assert len(asked(state)) == 2
    assert "This is denial 2 for this request" in reason_of(second)


def test_a_new_ask_resets_the_denial_count(state: HookSession) -> None:
    """A newer ask opens a fresh window; the count does not carry over."""
    assert run(state, tool_payload(transcript(state), HOST_DRIFT)).decision == "deny"
    tpath = transcript(state, [TASK], name="t3", prompt_at=LATER_PROMPT_AT)
    result = run(state, tool_payload(tpath, HOST_DRIFT))
    assert result.decision == "deny", result.output
    assert "This is denial 2" not in reason_of(result)


def test_reaching_the_correction_cap_allows(state: HookSession) -> None:
    tpath = transcript(state)
    assert (
        run(state, tool_payload(tpath, HOST_DRIFT), SCOPE_GUARD_CAP="1").decision
        == "deny"
    )
    result = run(
        state,
        tool_payload(tpath, "rm -rf ~/Library/Caches/x"),
        SCOPE_GUARD_CAP="1",
    )
    assert result.decision == "none", result.output
    assert len(asked(state)) == 1
    row = rows(state)[-1]
    assert row["decision"] == "allow"
    assert row["reason"] == "correction-cap-reached"
    assert row["scores"] == {}


# --- 5. everything the guard cannot judge fails open, and the log says why -----------


def test_the_bypass_env_allows_before_anything(state: HookSession) -> None:
    result = run(state, tool_payload(transcript(state), HOST_DRIFT), SCOPE_GUARD="off")
    assert result.decision == "none", result.output
    assert asked(state) == []
    row = rows(state)[-1]
    assert row["decision"] == "allow"
    assert row["reason"] == "guard-disabled"
    assert row["scores"] == {}


def test_no_user_task_allows(state: HookSession) -> None:
    result = run(state, tool_payload(transcript(state, []), HOST_DRIFT))
    assert result.decision == "none", result.output
    assert asked(state) == []
    row = rows(state)[-1]
    assert row["decision"] == "allow"
    assert row["reason"] == "no-user-task"
    assert row["scores"] == {}


def test_a_missing_transcript_allows(state: HookSession) -> None:
    result = run(state, tool_payload("/nonexistent/session.jsonl", HOST_DRIFT))
    assert result.decision == "none", result.output
    assert asked(state) == []
    row = rows(state)[-1]
    assert row["decision"] == "allow"
    assert row["reason"] == "no-user-task"


def test_a_hung_judge_times_out_and_allows(state: HookSession) -> None:
    result = run(
        state,
        tool_payload(transcript(state), HOST_DRIFT),
        mode="hang",
        HC_SCOPE_JUDGE_TIMEOUT_SECS="1",
    )
    assert result.decision == "none", result.output
    row = rows(state)[-1]
    assert row["decision"] == "allow"
    assert row["reason"] == "judge-timeout"
    assert row["scores"] == {}


@pytest.mark.parametrize(
    ("mode", "fallback"),
    [
        ("garbage", "judge-not-json"),
        ("no-source", "judge-source-unavailable"),
        ("no-noul", "judge-answer-OffTopic-invalid"),
        ("no-key", "judge-exit-1"),
        ("crash", "judge-exit-1"),
    ],
    ids=["garbage", "no-source", "no-noul", "no-key", "crash"],
)
def test_an_unusable_judge_allows_and_names_why(
    state: HookSession, mode: str, fallback: str
) -> None:
    result = run(state, tool_payload(transcript(state), HOST_DRIFT), mode=mode)
    assert result.decision == "none", result.output
    row = rows(state)[-1]
    assert row["decision"] == "allow"
    assert row["reason"] == fallback
    assert row["scores"] == {}


def test_an_unsupported_event_is_not_judged(state: HookSession) -> None:
    payload = {
        "session_id": "s-scope",
        "transcript_path": transcript(state),
        "cwd": "/tmp",
        "hook_event_name": "SubagentStop",
    }
    result = run(state, payload)
    assert result.decision == "none", result.output
    assert asked(state) == []
    row = rows(state)[-1]
    assert row["decision"] == "allow"
    assert row["reason"] == "unsupported-event"
