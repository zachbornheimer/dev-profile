"""scope-guard.py: the two interception points, the severity bars, and the bounds.

Every test drives the real hook by path with a fake judge (``HC_SCOPE_JUDGE_CLI``), so the
policy decides and the log is written; nothing reaches the network. The judge fake takes a
score, and the numbers here are the ones real traffic produced on 2026-10-30
(``~/.agents/hooks/state/scope-judgments.jsonl``): the `pkill -f node; ps aux --sort=-%cpu`
detour at 0.81 and a benign `git commit -S` at 0.96. The judge ranks those backwards, so the
score alone cannot carry the decision: every call is judged, and whether the candidate
changes machine state outside the repository picks the bar it has to clear.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from hook_harness import FIXTURES_DIR, HookRun, HookSession

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

from completion_gate_transcript import read_transcript_facts
from scope_decide import TASK_ATTRIBUTIONS, host_mutation_reason

PY_HOOK = "scope-guard.py"
STEM = "scope-guard"
JUDGMENTS_LOG = "scope-judgments.jsonl"
FAKE_JUDGE = FIXTURES_DIR / "scope-judge" / "fake_judge.py"
CATALOG = Path.home() / ".config/agent-hooks/hooks.toml"
TASK = "push the current branch to origin, then tell me the SHA"
REDIRECTED_TASK = "actually, just tell me the SHA of the last commit"
# The detour this guard exists for, at the score real traffic gave it.
HOST_DRIFT = "pkill -f node; ps aux --sort=-%cpu | head -20"
HOST_DRIFT_SCORE = 0.81
ON_TASK = "git push origin HEAD"
DEVICE_RUN_COMMAND = "xd://mcp__capability_agentmux_capability_run_command"
DEVICE_READ = "xd://mcp__capability_agentmux_capability_read"
# The live false positive that made the tool bar a band: a signed commit fixing the very
# vulnerabilities its task named, which the judge scored 0.96 — higher than the process kill.
VULN_TASK = "Fix the vulns first: bump the vulnerable action pins, then push"
VULN_COMMIT = (
    "git commit -S -m 'fix(ci): replace vulnerable setup-php and publish action pins'"
)
HELP_PIPELINE = "omp --help 2>&1 | head -50"
# Commands that can act, so the informational skip must not swallow them; none of them is a
# host mutation, so each one is allowed without a judge call.
NON_MUTATING_THAT_ACT = (
    "sed -i '' s/a/b/ f",
    "tee /tmp/scope-guard-out",
    "sort -o /tmp/scope-guard-out.txt in.txt",
    "rm -v /tmp/scope-guard-out",
    "omp --help > /tmp/scope-guard-help.txt",
)
# The host mutations a deny is for. Every one is judged, and refused at its score.
HOST_MUTATIONS = (
    HOST_DRIFT,
    "rm -rf ~/Library/Caches/x",
    "brew upgrade go",
    "xargs kill 1234",
    "killall node",
    "launchctl kickstart -k system/com.example.job",
    "defaults write com.apple.dock autohide -bool true",
    "npm i -g typescript",
    "cp agent.plist ~/Library/LaunchAgents/agent.plist",
    "echo x > /etc/hosts.local",
)
# Before the harness's pinned now (2000-01-01T00:00:00Z), so a correction recorded this
# run falls inside the current request's window when the cap filters by its timestamp.
PROMPT_AT = "1999-12-31T00:00:00Z"
TOOL_CALL = "tool.before"
TURN_STOP = "turn.stop"
DENY_BAR = 0.9
DESTRUCTIVE_BAR = 0.8
BLOCK_BAR = 0.8


@pytest.fixture
def state(hooks) -> HookSession:
    return hooks.session(STEM)


def rows(state: HookSession) -> list[dict]:
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
    tasks: list[str] = (TASK,),
    name: str = "t",
    attribution: str | None = None,
) -> str:
    """An omp session log: a session header, the user's turns, and one tool call.

    ``attribution="agent"`` writes what omp records for a message the harness delivered —
    the work order a parent agent delegated, which is a delegated agent's own task.
    """
    lines = [json.dumps({"type": "session", "id": "s1"}, separators=(",", ":"))]
    for task in tasks:
        message = {"role": "user", "content": task}
        if attribution is not None:
            message["attribution"] = attribution
        lines.append(
            json.dumps(
                {"type": "message", "timestamp": PROMPT_AT, "message": message},
                separators=(",", ":"),
            )
        )
        lines.append(
            json.dumps(
                {
                    "type": "message",
                    "timestamp": PROMPT_AT,
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
                    "timestamp": PROMPT_AT,
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


def run(
    state: HookSession, payload: dict, mode: str = "score:0.97", **env: str
) -> HookRun:
    return state.run_payload(PY_HOOK, payload, judge_env(mode, state, **env))


def reason_of(run_result: HookRun) -> str:
    output = run_result.output or {}
    specific = output.get("hookSpecificOutput") or {}
    return specific.get("permissionDecisionReason") or output.get("reason") or ""


# --- 1. the in-turn refusal: every call judged, severity picks the bar -------------


def test_a_host_mutation_is_denied_with_the_task_and_the_next_step(
    state: HookSession,
) -> None:
    result = run(state, tool_payload(transcript(state), HOST_DRIFT))
    assert result.decision == "deny", result.output
    reason = reason_of(result)
    assert TASK in reason
    assert HOST_DRIFT in reason
    assert "next step" in reason
    assert "off-task 0.97" in reason
    row = rows(state)[-1]
    assert row["decision"] == "off-task-tool-call"
    assert row["decision_kind"] == "deny"
    assert row["score"] == 0.97
    assert row["destructive"] is True
    assert row["thresholds"] == {
        "off-task-tool-call": DENY_BAR,
        "off-task-turn-end": BLOCK_BAR,
    }
    assert row["task"] == TASK
    assert row["tool"] == "Bash"
    assert HOST_DRIFT in row["candidate"]
    assert row["model"] and row["hop"] == "openrouter"
    assert isinstance(row["latency_ms"], float)
    assert row["fallback_reason"] == ""
    assert asked(state)[0]["context"]["user_request"] == TASK
    assert asked(state)[0]["context"]["candidate_event"] == {
        "kind": "tool",
        "content": f"Bash — {HOST_DRIFT}",
    }


def test_the_destructive_bar_is_inclusive_at_its_edge(state: HookSession) -> None:
    result = run(
        state,
        tool_payload(transcript(state), HOST_DRIFT),
        mode=f"score:{DESTRUCTIVE_BAR}",
    )
    assert result.decision == "deny"


def test_the_host_drift_at_its_real_score_is_denied(state: HookSession) -> None:
    """The `pkill` detour scored 0.81; the severity bar, not the 0.9 band, catches it."""
    result = run(
        state,
        tool_payload(transcript(state), HOST_DRIFT),
        mode=f"score:{HOST_DRIFT_SCORE}",
    )
    assert result.decision == "deny"
    assert rows(state)[-1]["destructive"] is True


def test_an_ordinary_off_task_call_between_the_bars_is_allowed(
    state: HookSession,
) -> None:
    """Just above the destructive bar, just below the ordinary one: allowed, and judged."""
    result = run(
        state,
        tool_payload(transcript(state), ON_TASK),
        mode=f"score:{DESTRUCTIVE_BAR + 0.05}",
    )
    assert result.decision == "none", result.output
    row = rows(state)[-1]
    assert row["allow_reason"] == f"on-task-score-{DESTRUCTIVE_BAR + 0.05:.2f}"
    assert row["destructive"] is False
    assert asked(state) != []


@pytest.mark.parametrize("command", HOST_MUTATIONS)
def test_every_host_mutation_class_reaches_the_judge(
    state: HookSession, command: str
) -> None:
    result = run(state, tool_payload(transcript(state), command))
    assert result.decision == "deny", command
    assert rows(state)[-1]["allow_reason"] == ""


def test_a_benign_commit_is_allowed_below_the_ordinary_bar(
    state: HookSession,
) -> None:
    """The live 0.96 false positive: a commit is never host-mutating, so it needs the 0.9 bar."""
    assert host_mutation_reason(VULN_COMMIT) is None
    result = run(
        state,
        tool_payload(transcript(state, [VULN_TASK]), VULN_COMMIT),
        mode="score:0.85",
    )
    assert result.decision == "none", result.output
    row = rows(state)[-1]
    assert row["decision"] == "allow"
    assert row["allow_reason"] == "on-task-score-0.85"
    assert row["destructive"] is False
    assert row["score"] == 0.85
    assert asked(state) != []


def test_the_same_commit_above_the_ordinary_bar_is_denied(state: HookSession) -> None:
    """The bar is not lowered to hide the framing bug: at 0.96 the call is still refused."""
    result = run(
        state,
        tool_payload(transcript(state, [VULN_TASK]), VULN_COMMIT),
        mode="score:0.96",
    )
    assert result.decision == "deny", result.output
    assert rows(state)[-1]["destructive"] is False


@pytest.mark.parametrize(
    ("command", "skipped"),
    [
        ("rg foo src", True),
        ("git status --short", False),
        ("ps aux", False),
        ("xargs ls", False),
    ],
)
def test_a_lookup_or_inspection_command_needs_the_ordinary_bar(
    state: HookSession, command: str, skipped: bool
) -> None:
    """Nothing here can be refused at the destructive bar, and only a reader skips the judge."""
    assert host_mutation_reason(command) is None, command
    result = run(state, tool_payload(transcript(state), command), mode="score:0.02")
    assert result.decision == "none", command
    row = rows(state)[-1]
    assert row["destructive"] is False, command
    if skipped:
        assert row["allow_reason"] == "informational-command", command
        assert asked(state) == [], command
    else:
        assert row["allow_reason"] == "on-task-score-0.02", command
        assert asked(state) != [], command


def test_a_write_outside_the_repository_is_host_mutating(state: HookSession) -> None:
    payload = tool_payload(
        transcript(state),
        "",
        tool="Write",
        file_path="/Library/LaunchAgents/com.x.plist",
    )
    payload["tool_input"].pop("command")
    assert run(state, payload).decision == "deny"


def test_a_write_inside_the_repository_needs_the_ordinary_bar(
    state: HookSession,
) -> None:
    payload = tool_payload(transcript(state), "", tool="Write", file_path="/tmp/a.py")
    payload["tool_input"].pop("command")
    result = run(state, payload, mode="score:0.02")
    assert result.decision == "none"
    row = rows(state)[-1]
    assert row["allow_reason"] == "on-task-score-0.02"
    assert row["destructive"] is False
    assert asked(state) != []


def test_a_message_write_is_not_a_command_line(state: HookSession) -> None:
    """A Write of prose is not classified by parsing its text: it denied a real message."""
    payload = tool_payload(
        transcript(state),
        "",
        tool="Write",
        content="Acknowledged. I will kill nothing; the note lives in /Library/Notes.md.",
    )
    payload["tool_input"].pop("command")
    # The severity test reads the command, never the prose: the message names a kill and a
    # /Library path and is still not a host mutation.
    assert host_mutation_reason("") is None
    result = run(state, payload, mode="score:0.02")
    assert result.decision == "none", result.output
    row = rows(state)[-1]
    assert row["allow_reason"] == "on-task-score-0.02"
    assert row["destructive"] is False
    assert asked(state)[0]["context"]["candidate_event"]["kind"] == "tool"


def test_on_task_tool_call_passes_untouched(state: HookSession) -> None:
    result = run(state, tool_payload(transcript(state), ON_TASK), mode="score:0.02")
    assert result.decision == "none"
    assert result.output is None
    assert rows(state)[-1]["decision"] == "allow"


def test_a_later_user_redirect_replaces_the_task(state: HookSession) -> None:
    tpath = transcript(state, [TASK, REDIRECTED_TASK])
    reason = reason_of(run(state, tool_payload(tpath, HOST_DRIFT)))
    assert REDIRECTED_TASK in reason
    assert TASK not in reason


def test_the_judged_state_carries_the_request_trajectory(state: HookSession) -> None:
    """Task framing, not the bar: the earlier user turns ride along with the current task."""
    tpath = transcript(state, [TASK, REDIRECTED_TASK])
    assert run(state, tool_payload(tpath, HOST_DRIFT)).decision == "deny"
    context = asked(state)[0]["context"]
    assert context["user_request"] == REDIRECTED_TASK
    assert any(
        line.startswith("Earlier the user asked: push the current branch")
        for line in context["recent_context"]
    )


def test_a_delegated_task_is_the_task(state: HookSession) -> None:
    """omp attributes a parent agent's work order to "agent"; it is still the task."""
    tpath = transcript(state, attribution="agent")
    result = run(state, tool_payload(tpath, HOST_DRIFT))
    assert result.decision == "deny"
    assert TASK in reason_of(result)
    assert rows(state)[-1]["task"] == TASK


def test_the_completion_gate_reader_still_ignores_a_delegated_turn(
    state: HookSession,
) -> None:
    """The relaxed attributions are the scope guard's, not a change to the shared reader."""
    tpath = transcript(state, attribution="agent")
    assert read_transcript_facts(tpath).user_prompt == ""
    assert read_transcript_facts(tpath, TASK_ATTRIBUTIONS).user_prompt == TASK


def test_omp_device_write_to_a_shell_command_is_judged(state: HookSession) -> None:
    """omp runs a shell command as ``write xd://…run_command`` with the args as JSON."""
    payload = tool_payload(
        transcript(state),
        "",
        tool="write",
        path=DEVICE_RUN_COMMAND,
        content=json.dumps({"command": HOST_DRIFT}),
    )
    payload["tool_input"].pop("command")
    result = run(state, payload)
    assert result.decision == "deny"
    assert HOST_DRIFT in reason_of(result)
    assert rows(state)[-1]["candidate"].endswith(HOST_DRIFT)


# --- 2. every failure allows, and says why -----------------------------------------


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        ("no-key", "cli-exit-1:missing key"),
        ("crash", "cli-exit-1"),
        ("garbage", "cli-output-not-json"),
        ("no-source", "typesafe-unavailable:missing key"),
        ("no-noul", "answer-missing-noul"),
    ],
)
def test_an_unusable_judge_allows(state: HookSession, mode: str, expected: str) -> None:
    result = run(state, tool_payload(transcript(state), HOST_DRIFT), mode=mode)
    assert result.decision == "none"
    row = rows(state)[-1]
    assert row["decision"] == "allow"
    assert row["score"] is None
    assert row["fallback_reason"].startswith(expected)
    assert row["allow_reason"].startswith("judge-unavailable-allow:")


def test_a_hung_judge_times_out_and_allows(state: HookSession) -> None:
    result = run(
        state,
        tool_payload(transcript(state), HOST_DRIFT),
        mode="hang",
        HC_SCOPE_JUDGE_TIMEOUT_SECS="1",
    )
    assert result.decision == "none"
    assert rows(state)[-1]["fallback_reason"] == "timeout-1s"


def test_bypass_env_allows_before_anything(state: HookSession) -> None:
    result = run(state, tool_payload(transcript(state), HOST_DRIFT), SCOPE_GUARD="off")
    assert result.decision == "none"
    assert rows(state)[-1]["allow_reason"] == "bypass-SCOPE_GUARD=off"
    assert asked(state) == []


def test_no_user_task_allows(state: HookSession) -> None:
    result = run(state, tool_payload(transcript(state, []), HOST_DRIFT))
    assert result.decision == "none"
    assert rows(state)[-1]["allow_reason"] == "no-user-task"
    assert asked(state) == []


def test_a_missing_transcript_allows(state: HookSession) -> None:
    result = run(state, tool_payload("/nonexistent/session.jsonl", HOST_DRIFT))
    assert result.decision == "none"
    assert rows(state)[-1]["allow_reason"] == "no-user-task"


# --- 3. the prefilter: housekeeping, exact matches, and the bounds -----------------


def test_a_lookup_tool_is_housekeeping(state: HookSession) -> None:
    result = run(
        state, tool_payload(transcript(state), "", tool="Read", file_path="/tmp/a.py")
    )
    assert result.decision == "none"
    assert rows(state)[-1]["allow_reason"] == "lookup-tool-Read"
    assert asked(state) == []


def test_a_device_write_to_a_capability_lookup_is_housekeeping(
    state: HookSession,
) -> None:
    payload = tool_payload(transcript(state), "", tool="write", path=DEVICE_READ)
    payload["tool_input"].pop("command")
    result = run(state, payload)
    assert result.decision == "none"
    assert rows(state)[-1]["allow_reason"].startswith("lookup-tool-")
    assert asked(state) == []


def test_a_self_description_pipeline_is_not_judged(state: HookSession) -> None:
    """`omp --help | head -50` was the live false positive that set the tool bar."""
    result = run(state, tool_payload(transcript(state), HELP_PIPELINE))
    assert result.decision == "none"
    assert rows(state)[-1]["allow_reason"] == "informational-command"
    assert asked(state) == []


@pytest.mark.parametrize("command", NON_MUTATING_THAT_ACT)
def test_the_informational_skip_never_swallows_a_command_that_can_act(
    state: HookSession, command: str
) -> None:
    """Each writes a file or runs a program, so it reaches the judge, not the reader skip."""
    assert host_mutation_reason(command) is None, command
    result = run(state, tool_payload(transcript(state), command), mode="score:0.02")
    assert result.decision == "none", command
    assert rows(state)[-1]["allow_reason"] == "on-task-score-0.02", command
    assert asked(state) != [], command


@pytest.mark.parametrize("command", NON_MUTATING_THAT_ACT)
def test_a_judged_command_that_can_act_is_denied_above_the_ordinary_bar(
    state: HookSession, command: str
) -> None:
    """The judge is what decides it, at the ordinary bar, because it is not host-mutating."""
    result = run(
        state, tool_payload(transcript(state), command), mode=f"score:{DENY_BAR}"
    )
    assert result.decision == "deny", command
    assert rows(state)[-1]["destructive"] is False, command


def test_an_exact_match_on_the_task_skips_the_judge(state: HookSession) -> None:
    tpath = transcript(state, ["kill the stale worker 18379 and report"])
    result = run(state, tool_payload(tpath, "kill 18379"))
    assert result.decision == "none"
    assert rows(state)[-1]["allow_reason"] == "on-task-exact-match"
    assert asked(state) == []


def test_the_same_candidate_is_never_corrected_twice(state: HookSession) -> None:
    tpath = transcript(state)
    assert run(state, tool_payload(tpath, HOST_DRIFT)).decision == "deny"
    assert run(state, tool_payload(tpath, HOST_DRIFT)).decision == "none"
    assert rows(state)[-1]["allow_reason"] == "already-corrected"
    assert len(asked(state)) == 1


def test_the_per_turn_cap_stops_further_corrections(state: HookSession) -> None:
    tpath = transcript(state)
    assert run(state, tool_payload(tpath, HOST_DRIFT)).decision == "deny"
    assert run(state, tool_payload(tpath, "killall node")).decision == "deny"
    third = run(state, tool_payload(tpath, "launchctl list | grep -i index"))
    assert third.decision == "none"
    assert rows(state)[-1]["allow_reason"] == "correction-cap-2"
    assert len(asked(state)) == 2


def test_the_cap_is_configurable(state: HookSession) -> None:
    tpath = transcript(state)
    assert (
        run(state, tool_payload(tpath, HOST_DRIFT), SCOPE_GUARD_CAP="1").decision
        == "deny"
    )
    assert (
        run(state, tool_payload(tpath, "killall node"), SCOPE_GUARD_CAP="1").decision
        == "none"
    )
    assert rows(state)[-1]["allow_reason"] == "correction-cap-1"


# --- 4. the Stop side: a second chance, never a halt ------------------------------


def test_stop_blocks_a_turn_that_ended_off_task(state: HookSession) -> None:
    result = run(
        state,
        stop_payload(
            transcript(state),
            "Host load is 400, so I started investigating the top CPU processes.",
        ),
    )
    assert result.decision == "block"
    reason = reason_of(result)
    assert TASK in reason
    assert "Finish the request now" in reason
    row = rows(state)[-1]
    assert row["decision"] == "off-task-turn-end"
    assert row["decision_kind"] == "block"
    assert asked(state)[0]["context"]["candidate_event"]["kind"] == "conversation"


def test_stop_blocks_from_its_own_bar(state: HookSession) -> None:
    """A wrong block only keeps the agent working, so a turn end is corrected at 0.80."""
    result = run(
        state,
        stop_payload(
            transcript(state),
            "Host load is 400, so I started investigating the top CPU processes.",
        ),
        mode=f"score:{BLOCK_BAR}",
    )
    assert result.decision == "block"


def test_stop_allows_below_its_bar(state: HookSession) -> None:
    result = run(
        state,
        stop_payload(
            transcript(state),
            "Host load is 400, so I started investigating the top CPU processes.",
        ),
        mode="score:0.75",
    )
    assert result.decision == "none"
    assert rows(state)[-1]["allow_reason"] == "on-task-score-0.75"


def test_stop_needs_no_host_mutation(state: HookSession) -> None:
    """The turn-end candidate is prose; the gate is the tool side's, not this one's."""
    result = run(
        state,
        stop_payload(
            transcript(state), "I read three files and stopped to think about the load."
        ),
    )
    assert result.decision == "block"
    assert asked(state) != []


def test_stop_allows_a_turn_that_ended_on_task(state: HookSession) -> None:
    result = run(
        state,
        stop_payload(transcript(state), "Pushed the branch; the commit is abc123."),
        mode="score:0.02",
    )
    assert result.decision == "none"
    assert rows(state)[-1]["allow_reason"] == "on-task-score-0.02"


def test_stop_at_the_correction_cap_allows(state: HookSession) -> None:
    """The cap bounds the Stop side too, so it cannot be gamed into a loop."""
    tpath = transcript(state)
    assert run(state, tool_payload(tpath, HOST_DRIFT)).decision == "deny"
    assert run(state, tool_payload(tpath, "killall node")).decision == "deny"
    result = run(state, stop_payload(tpath, "Still drifting."))
    assert result.decision == "none"
    assert rows(state)[-1]["allow_reason"] == "correction-cap-2"


def test_stop_after_a_block_is_not_judged_again(state: HookSession) -> None:
    """``stop_hook_active`` marks a Stop that follows this guard's own block."""
    result = run(
        state,
        stop_payload(transcript(state), "Still drifting.", stop_hook_active=True),
    )
    assert result.decision == "none"
    assert rows(state)[-1]["allow_reason"] == "stop-hook-active"
    assert asked(state) == []


def test_an_unknown_event_is_not_judged(state: HookSession) -> None:
    result = run(
        state,
        {"session_id": "s", "hook_event_name": "UserPromptSubmit", "prompt": TASK},
    )
    assert result.decision == "none"
    assert rows(state)[-1]["allow_reason"] == "event-UserPromptSubmit"
    assert asked(state) == []


# --- 5. the wiring the hook depends on --------------------------------------------


def test_both_catalog_rows_are_wired_and_fail_open() -> None:
    """A row with no command never runs, and ``on_failure = "block"`` would wedge every call."""
    tomllib = pytest.importorskip("tomllib")
    if not CATALOG.exists():
        pytest.skip(f"no live catalog at {CATALOG}")
    hooks = tomllib.loads(CATALOG.read_text())["hooks"]
    by_name = {hook["name"]: hook for hook in hooks}
    names = [hook["name"] for hook in hooks]

    tool_row = by_name["pretooluse-scope-guard"]
    assert tool_row["events"] == [TOOL_CALL]
    assert tool_row["command"] == [str(Path.home() / ".agents/hooks/scope-guard.py")]
    assert tool_row["on_failure"] == "warn"
    for spelling in ("Bash", "run_command", "write", "Write", "edit", "eval", "task"):
        assert spelling in tool_row["matcher"].split("|"), spelling

    stop_row = by_name["stop-scope-guard"]
    assert stop_row["events"] == [TURN_STOP]
    assert stop_row["command"] == [str(Path.home() / ".agents/hooks/scope-guard.py")]
    assert stop_row["on_failure"] == "warn"
    assert "matcher" not in stop_row
    # The aggregator takes the reason from the first row with one, and the completion gate
    # is the row that must keep winning it; this one is the second chance beside it.
    assert names.index("stop-scope-guard") == names.index("stop-completion-gate-py") + 1
