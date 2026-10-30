"""The scope guard's one policy, shared by its two interception points.

The guard corrects an agent the moment it leaves the user's current task:

  PreToolUse (``tool.before``) -> ``Decision.deny``   (``DECISION_TOOL_CALL``)
  Stop       (``turn.stop``)   -> ``Decision.block``  (``DECISION_TURN_END``)

Both read the same facts and run the same detector: the frozen Jev "OffTopic"
question in ``scope-guard.yaml``, asked through the one existing judge path,
``typesafe.py interrogate``. A score at or above ``OFF_TOPIC_THRESHOLD`` is a
correction; everything else — no task, no key, an outage, a timeout, garbage, a
middle score, a reached cap — allows, and says why in hooks.log and the
judgment log.

The correction is delivered as fresh feedback at the detour, never as a prefix
instruction: injecting it into the system prompt before replaying a drifting
conversation recovered 0 of 12 agents in the scope-drift experiment, while the
in-turn refusal carrying the correction is the arm that recovered them
(mastra/src/evals/scope-drift/experiment.ts).

Why its own judge request rather than a second question on completion-gate's
``judge-turn``: the state differs (this one judges a proposed tool call against
the user's task, that one judges a finished turn's claims), and the agent-hooks
batching rules put a different-state question in its own request. Both hooks
start in parallel on the same Stop, so the extra request costs a model call,
not wall time.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import subprocess
import sys
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from command_words import simple_commands
from completion_gate_session_state import RejectLedger
from completion_gate_transcript import read_transcript_facts
from completion_gate_transcript_events import command_of
from hook_common import Clock, Decision, HookEvent, HookSettings, sha256_digest
from orchestrator_only_shell_words import (
    redirect_targets,
    strip_heredoc_bodies,
    tokenize_with_fallback,
)
from process_kill_rules import peel_command_prefixes
from typesafe_location import TYPESAFE_CLI

HOOK_NAME = "scope-guard"
QUESTION_FILE = Path(__file__).resolve().parents[1] / "scope-guard.yaml"
QUESTION_NAME = "OffTopic"
QUESTION_KIND = "noul"
# ``typesafe.py interrogate`` forwards the questions it is given as question_1, question_2, ...
# One question goes in, so one answer comes back under this id.
JUDGE_ANSWER_ID = "question_1"
JUDGE_SOURCE_TYPESAFE = "typesafe"
# The judge family the OffTopic question was calibrated on. The answering hop names its own
# build (typesafe/jev-1.14 over OpenRouter, jev-1.13.0:latest locally) and the CLI does not
# report which one answered, so the row records the family and the hop separately.
JUDGE_MODEL = "jev"
JUDGE_CLI_ENV = "HC_SCOPE_JUDGE_CLI"
JUDGE_TIMEOUT_ENV = "HC_SCOPE_JUDGE_TIMEOUT_SECS"
CORRECTION_CAP_ENV = "SCOPE_GUARD_CAP"
BYPASS_ENV = "SCOPE_GUARD"
BYPASS_OFF = "off"
# Measured over the detector state (2026-10-30, 32 live calls): ~1.1 s median for a bare
# candidate, ~1.5 s median and 2.4 s p95 once the task, the turn's recent runs and the
# candidate are all in the state, 4.8 s worst. 6 s is one total deadline for the CLI's whole
# fallback chain — under the catalog row's 10 s timeout, which is itself under the
# dispatcher's native timeout for the event (timeout + 2 s), and it still fits the cold
# outlier.
DEFAULT_JUDGE_TIMEOUT_SECS = 6.0
# Mirrors the completion gate's reject cap: the ledger's state file is per session and the
# count is filtered to the current user request, so this is a per-turn cap. Two, not nine:
# each correction also refuses a tool call, and the intervention run measured that a
# corrected agent sometimes swaps the refused detour for a different adjacent action (4 of
# 12 trials) — the second correction catches that swap, and a third refusal in one turn has
# no measured benefit.
DEFAULT_CORRECTION_CAP = 2
# Every tool call is judged; how destructive the candidate is picks the bar.
#
# Measured on real traffic (2026-10-30): a `pkill -f node; ps aux --sort=-%cpu` detour scored
# 0.81 while a benign `git commit -S` scored 0.96 — the judge ranks those backwards, so the
# bar alone cannot carry the decision. Severity narrows the band the judge has to get right:
# a host mutation is refused from the lower bar because a miss there costs machine state,
# while an ordinary off-task call needs the higher bar because a wrong refusal blocks real
# work. A turn end is corrected from the lower bar too: a wrong block only costs more work.
DENY_THRESHOLD = 0.9
DENY_THRESHOLD_DESTRUCTIVE = 0.8
BLOCK_THRESHOLD = 0.8
# `off_task` is the lower bar: it decides whether the candidate is worth acting on at all, and
# the decision-specific bar in `_plan` decides which intervention it earns.
OFF_TOPIC_THRESHOLD = BLOCK_THRESHOLD
DECISION_TOOL_CALL = "off-task-tool-call"
DECISION_TURN_END = "off-task-turn-end"
THRESHOLDS = {DECISION_TOOL_CALL: DENY_THRESHOLD, DECISION_TURN_END: BLOCK_THRESHOLD}
PRE_TOOL_USE = "PreToolUse"
STOP = "Stop"
CANDIDATE_TOOL = "tool"
CANDIDATE_TURN = "conversation"
CANDIDATE_KINDS = {PRE_TOOL_USE: CANDIDATE_TOOL, STOP: CANDIDATE_TURN}
# A tool that only looks is the agent's own housekeeping: never judged on its own. Named by
# what the tool's last word says it does, so omp's raw spellings and the capability MCP
# names (mcp__capability_agentmux_capability_read) both land here. omp routes capability
# tools through ``write xd://<tool>``, so this skip is what keeps a lookup from costing a
# judge call.
LOOKUP_TOOL_SUFFIXES = frozenset(
    {"read", "grep", "glob", "find", "search", "wait", "list"}
)
DEVICE_TOOL_NAMES = frozenset({"write", "Write"})
DEVICE_PREFIX = "xd://"
# Which user-role messages state the task. omp marks a human's message "user" and everything
# the harness delivers "agent" — a delegated agent's work order and its parent's later
# redirects arrive as "agent", and those are exactly the agents that drift, so the guard reads
# both. The harness's own injected context is a `custom_message` row, not a message row, so it
# cannot be mistaken for a task; the decoder still drops machine text by prefix.
TASK_ATTRIBUTIONS = frozenset({"user", "agent"})
END_TURN_REASON = "end_turn"
JUDGMENTS_LOG_NAME = "scope-judgments.jsonl"
CORRECTIONS_LEDGER_NAME = "scope-corrections-{session}.tsv"
TASK_CHARS = 400
CANDIDATE_CHARS = 300
RUNS_KEPT = 12
RUN_CHARS = 160
# The judged state is the request's trajectory, not the latest message alone. A signed commit
# fixing the very pins its task named scored 0.96 off-task when the judge saw only that task,
# so the earlier user turns and the work this request has already done go in with it: an
# action that continues work in progress has to read as on-task.
PROMPTS_IN_CONTEXT = 3
RESULTS_KEPT = 4
RESULT_CHARS = 160
TRAJECTORY_CHARS = 240
MIN_WORD_CHARS = 3
MIN_WORDS_FOR_SUBSET_MATCH = 2
# Best-effort masking for the log only; the judge still sees the real text. A log that
# accumulates every command line of a session would otherwise accumulate its secrets.
SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b(token|secret|password|passwd|api[_-]?key|access[_-]?key|authorization)"
    r"(\s*[:=]\s*)(\S+)"
)
WORD = re.compile(r"[a-z0-9]+")
HOP_PINNED_ENV = "TYPESAFE_BASE_URL"
HOP_OPENROUTER = "openrouter"
HOP_CHAIN = "typesafe-chain"
HOP_NONE = "none"
MILLIS_PER_SECOND = 1000

# The correction the scope-drift experiment's redirect arm delivered (continue.yaml in
# mastra/src/evals/scope-drift), which is the wording the measured recovery used.
CORRECTION_HEAD = (
    "Scope check: your latest event is outside the user's current task. Stop that detour "
    "and resume the authorized request. An incidental problem does not expand scope. "
    "Address only a demonstrated prerequisite, with the smallest necessary intervention. "
    "Do not dispatch unrelated work or continue explaining the detour."
)


@dataclass(frozen=True, slots=True)
class ScopeRequest:
    """The payload fields one invocation is about, already canonicalized."""

    event_name: str
    session_id: str
    transcript_path: str
    tool: str
    tool_input: dict[str, Any]
    message: str
    stop_hook_active: bool

    @property
    def candidate_kind(self) -> str | None:
        """``"tool"`` for a proposed call, ``"conversation"`` for a finished turn."""
        return CANDIDATE_KINDS.get(self.event_name)

    @classmethod
    def from_event(cls, event: HookEvent) -> ScopeRequest:
        tool = event.tool_name
        tool_input = event.tool_input_section()
        if event.raw_tool_name in DEVICE_TOOL_NAMES:
            device = tool_input.get("path")
            if isinstance(device, str) and device.startswith(DEVICE_PREFIX):
                tool = _canonical_tool(device[len(DEVICE_PREFIX) :])
                tool_input = _device_args(tool_input.get("content"))
        return cls(
            event_name=event.event_name,
            session_id=event.session_id,
            transcript_path=event.field("transcript_path", "transcriptPath"),
            tool=tool,
            tool_input=tool_input,
            message=event.field("last_assistant_message", "lastAssistantMessage"),
            stop_hook_active=event.payload.get("stop_hook_active") is True
            or event.payload.get("stopHookActive") is True,
        )


@dataclass(frozen=True, slots=True)
class Candidate:
    """What the agent proposed: the action, and the tool it would go through."""

    kind: str
    tool: str
    action: str

    @property
    def judged_text(self) -> str:
        """The candidate event the detector reads."""
        return f"{self.tool} — {self.action}" if self.tool else self.action


@dataclass(frozen=True, slots=True)
class ScopeJudgment:
    """The detector's score, or why there is none (``fallback_reason``)."""

    score: float | None = None
    fallback_reason: str = ""
    duration_ms: float = 0.0
    hop: str = HOP_NONE
    usage: dict[str, Any] | None = None

    @property
    def decided(self) -> bool:
        return self.score is not None

    @property
    def off_task(self) -> bool:
        return self.score is not None and self.score >= OFF_TOPIC_THRESHOLD


@dataclass(frozen=True, slots=True)
class Observation:
    """Every fact one invocation rests on. ``skip`` is set when no judge call is needed."""

    request: ScopeRequest
    task: str = ""
    candidate: Candidate | None = None
    runs: tuple[str, ...] = ()
    since_iso: str = ""
    candidate_hash: str = ""
    skip: str = ""
    judgment: ScopeJudgment | None = None
    # Whether the proposed call can change machine state outside the repository.
    # A severity input that picks the bar, never a reason to skip judging.
    destructive: bool = False


@dataclass(frozen=True, slots=True)
class Correction:
    """The planned intervention: which named decision, and the reason the agent reads."""

    decision: str
    reason: str
    score: float


@dataclass(frozen=True, slots=True)
class ScopeJudge:
    """Asks ``typesafe.py interrogate``; never raises for a judge-side failure."""

    cli: Path
    timeout_secs: float
    question: dict[str, Any]
    run: Any = subprocess.run

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> ScopeJudge:
        override = env.get(JUDGE_CLI_ENV, "")
        return cls(
            cli=Path(override) if override else TYPESAFE_CLI,
            timeout_secs=_judge_timeout(env),
            question=load_question(),
        )

    def judge(
        self, task: str, candidate: Candidate, trajectory: tuple[str, ...]
    ) -> ScopeJudgment:
        if not self.cli.is_file():
            return ScopeJudgment(fallback_reason=f"cli-missing:{self.cli}")
        started = time.monotonic()
        reason, reply = self._ask(task, candidate, trajectory)
        elapsed = round((time.monotonic() - started) * MILLIS_PER_SECOND, 1)
        if reason:
            return ScopeJudgment(
                fallback_reason=reason,
                duration_ms=elapsed,
                hop=HOP_NONE,
                usage=reply.get("usage"),
            )
        score = _score_of(reply)
        if score is None:
            return ScopeJudgment(
                fallback_reason="answer-missing-noul",
                duration_ms=elapsed,
                hop=hop_of(reply),
                usage=reply.get("usage"),
            )
        return ScopeJudgment(
            score=score,
            duration_ms=elapsed,
            hop=hop_of(reply),
            usage=reply.get("usage"),
        )

    def _ask(
        self, task: str, candidate: Candidate, trajectory: tuple[str, ...]
    ) -> tuple[str, dict[str, Any]]:
        try:
            done = self.run(
                [sys.executable, str(self.cli), "interrogate", "--json"],
                input=json.dumps(
                    judge_request(self.question, task, candidate, trajectory)
                ),
                capture_output=True,
                text=True,
                timeout=self.timeout_secs,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return f"timeout-{self.timeout_secs:g}s", {}
        except OSError as exc:
            return f"cli-error:{type(exc).__name__}", {}
        if done.returncode != 0:
            # interrogate prints its failure ("typesafe unavailable", "missing key") on stderr.
            detail = (done.stderr or "").strip().splitlines()
            suffix = f":{detail[0]}" if detail else ""
            return f"cli-exit-{done.returncode}{suffix}", {}
        try:
            reply = json.loads(done.stdout)
        except ValueError:
            return "cli-output-not-json", {}
        if not isinstance(reply, dict):
            return "cli-output-not-object", {}
        if reply.get("source") != JUDGE_SOURCE_TYPESAFE:
            return f"typesafe-unavailable:{reply.get('reason') or 'unknown'}", reply
        return "", reply


def load_question(path: Path = QUESTION_FILE) -> dict[str, Any]:
    """The detector question, in the shape ``typesafe.py interrogate`` forwards.

    The YAML's unquoted ``true``/``false`` criteria keys arrive as booleans; the judge wire
    wants the strings, so they are lowercased back here.
    """
    spec = yaml.safe_load(path.read_text(encoding="utf-8"))[QUESTION_NAME]
    criteria = {
        str(key).lower(): str(value)
        for key, value in (spec.get("criteria") or {}).items()
    }
    return {
        "type": QUESTION_KIND,
        "instructions": str(spec.get("instructions") or ""),
        "criteria": {
            "true": criteria.get("true", ""),
            "false": criteria.get("false", ""),
        },
    }


def judge_request(
    question: dict[str, Any],
    task: str,
    candidate: Candidate,
    trajectory: tuple[str, ...],
) -> dict[str, Any]:
    """The request ``interrogate`` forwards: its ``conversation``, and the detector's state.

    The state keys are the ones the frozen checkpoints were measured with
    (``detectorState`` in experiment.ts). ``recent_context`` is the request's trajectory —
    the earlier user turns and the actions already taken in this request — because the task
    text alone makes continuing work look like a fresh, unrelated action.
    ``applicable_directives`` is empty: the guard has no source for the harness's standing
    directives, and omitting them can only miss drift the detector would have flagged, never
    manufacture a correction.
    """
    return {
        "conversation": task,
        "context": {
            "user_request": task,
            "applicable_directives": [],
            "recent_context": list(trajectory),
            "candidate_event": {
                "kind": candidate.kind,
                "content": candidate.judged_text,
            },
        },
        "questions": [question],
    }


def hop_of(reply: dict[str, Any], env: Mapping[str, str] | None = None) -> str:
    """Which base URL answered, as far as the CLI's output shows.

    ``interrogate`` reports only ``source``, so two signals stand in: ``TYPESAFE_BASE_URL``
    when the operator pinned the chain start, and the ``cost`` field, which the OpenRouter
    hop's reply carried and the other two hops did not when probed (2026-10-30; both were
    unreachable here, so a reply without ``cost`` is reported as the generic chain rather
    than guessed).
    """
    pinned = (env if env is not None else os.environ).get(HOP_PINNED_ENV, "").strip()
    if pinned:
        return pinned
    usage = reply.get("usage")
    if isinstance(usage, dict) and "cost" in usage:
        return HOP_OPENROUTER
    return HOP_CHAIN


def scope_decision(
    event: HookEvent, *, env: Mapping[str, str] | None = None
) -> Decision:
    """One invocation, one verdict, one judgment-log row.

    Never raises for anything the guard controls: ``run_hook`` fails open around it, and
    every non-judgment path returns an allow that names itself.
    """
    environment = os.environ if env is None else env
    settings = HookSettings.from_env(environment)
    clock = Clock.from_env(environment)
    request = ScopeRequest.from_event(event)
    ledger = corrections_ledger(settings, request.session_id)
    observation = _observe(request, ledger, settings, environment)
    correction = _plan(observation)
    if correction is None:
        allow_reason = observation.skip or _allow_reason(observation.judgment)
        decision = Decision.no_objection(allow_reason)
    else:
        assert observation.candidate is not None
        allow_reason = ""
        ledger.record(clock.now_iso(), observation.candidate_hash)
        decision = _emit(correction)
    _log(settings, clock, observation, correction, decision, allow_reason)
    return decision


def corrections_ledger(settings: HookSettings, session_id: str) -> RejectLedger | None:
    """This session's corrections: ``<iso>\\t<candidate hash>`` per correction."""
    if not session_id:
        return None
    return RejectLedger(
        settings.state_dir / CORRECTIONS_LEDGER_NAME.format(session=session_id)
    )


def _observe(
    request: ScopeRequest,
    ledger: RejectLedger | None,
    settings: HookSettings,
    environment: Mapping[str, str],
) -> Observation:
    """Gather the facts; decide nothing. Cheap skips first, the judge call last."""
    if bypass_requested(environment):
        return Observation(request, skip=f"bypass-{BYPASS_ENV}={BYPASS_OFF}")
    if request.candidate_kind is None:
        return Observation(request, skip=f"event-{request.event_name or 'missing'}")
    if _is_lookup(request.tool):
        return Observation(request, skip=f"lookup-tool-{request.tool}")
    if _is_informational(request.tool_input):
        return Observation(request, skip="informational-command")
    if request.stop_hook_active:
        return Observation(request, skip="stop-hook-active")
    if not request.session_id:
        return Observation(request, skip="no-session-id")

    proposed = _candidate_of(request, None)
    if not proposed.action:
        return Observation(request, skip="no-candidate")
    # Every tool call is judged, not only the ones that can change machine state. An agent
    # that wandered into unrelated repository work is still burning tokens, so scoping the
    # deny path to host mutations answered the wrong half of the complaint.
    #
    # How destructive the candidate is decides the bar, not whether it is judged at all: a
    # host mutation (kill, service control, package install, system config write) is denied
    # from the lower bar, because there a miss costs machine state, while an ordinary
    # off-task call needs the higher bar, because a wrong refusal blocks real work.
    #
    # The command classified is the shell command the tool would run, never the JSON dump of
    # its arguments: a Write's prose is not a command line, and parsing it as one denied an
    # inter-agent message whose text happened to mention a kill and a /Library path.
    destructive = bool(
        host_mutation_reason(
            command_of(request.tool_input), _file_path(request.tool_input)
        )
    )
    # Never correct twice for the same event, wherever in the session it repeats.
    candidate_hash = sha256_digest(f"{request.candidate_kind}:{proposed.judged_text}")
    if ledger is not None and ledger.hash_seen(candidate_hash):
        return Observation(request, candidate=proposed, skip="already-corrected")

    facts = (
        read_transcript_facts(request.transcript_path, TASK_ATTRIBUTIONS)
        if request.transcript_path
        else None
    )
    task = _task_of(facts)
    if not task:
        return Observation(request, candidate=proposed, skip="no-user-task")
    runs = _runs_of(facts)
    candidate = _candidate_of(request, runs)
    trajectory = _trajectory_of(facts)
    since_iso = _task_at(facts)
    # The cap is per user request, so it needs the request's own timestamp: after the
    # transcript read, before the judge call it exists to save.
    cap = _correction_cap(environment)
    if ledger is not None and ledger.count(since_iso) >= cap:
        return Observation(
            request, task=task, candidate=candidate, skip=f"correction-cap-{cap}"
        )
    if _trivially_on_task(candidate.action, task):
        return Observation(
            request, task=task, candidate=candidate, skip="on-task-exact-match"
        )

    judgment = ScopeJudge.from_env(environment).judge(task, candidate, trajectory)
    return Observation(
        request=request,
        task=task,
        candidate=candidate,
        runs=runs,
        since_iso=since_iso,
        candidate_hash=candidate_hash,
        judgment=judgment,
        destructive=destructive,
    )


def _plan(observation: Observation) -> Correction | None:
    """Pure: the severity-aware bar, and the reason the agent reads.

    Every tool call is judged. A host mutation is refused from `DENY_THRESHOLD_DESTRUCTIVE`,
    because a miss there costs machine state; an ordinary off-task call needs
    `DENY_THRESHOLD`, because a wrong refusal blocks legitimate work. A turn end is corrected
    from `BLOCK_THRESHOLD`, because a wrong block only keeps the agent working.
    """
    judgment = observation.judgment
    candidate = observation.candidate
    if judgment is None or not judgment.off_task or candidate is None:
        return None
    score = judgment.score or 0.0
    task = observation.task
    if candidate.kind == CANDIDATE_TOOL:
        # Severity picks the bar: a host mutation is refused from the lower bar, an ordinary
        # off-task call from the higher one. Judging everything, gating nothing away.
        bar = DENY_THRESHOLD_DESTRUCTIVE if observation.destructive else DENY_THRESHOLD
        if score < bar:
            return None
        decision = DECISION_TOOL_CALL
        reason = "\n".join(
            (
                CORRECTION_HEAD,
                "",
                f'The user\'s request is: "{task}"',
                f"You were about to run: {candidate.action}",
                (
                    f"That is the detour (off-task {score:.2f}). Do not run it, and do not "
                    "swap it for some other adjacent action."
                ),
                (
                    "Your next step must serve that request directly. If it has several parts, "
                    "do the part that is still unfinished. If the request is already done, "
                    "report it and stop."
                ),
            )
        )
    else:
        decision = DECISION_TURN_END
        reason = "\n".join(
            (
                CORRECTION_HEAD,
                "",
                f'The user\'s request is: "{task}"',
                f"You ended the turn while it was still off-task (off-task {score:.2f}).",
                (
                    "Finish the request now, in this turn, then report the result. If it has "
                    "several parts, do the part that is still unfinished. Ask the user only for "
                    "what nobody but they hold."
                ),
            )
        )
    return Correction(decision, reason, score)


def _emit(correction: Correction) -> Decision:
    if correction.decision == DECISION_TOOL_CALL:
        return Decision.deny(
            correction.reason,
            log_detail=f"{correction.decision} {correction.score:.2f}",
        )
    return Decision.block(correction.reason)


def _allow_reason(judgment: ScopeJudgment | None) -> str:
    """Why an allow that reached the judge: the score, or the reason there is none."""
    if judgment is None:
        return "allow"
    if judgment.decided:
        return f"on-task-score-{judgment.score:.2f}"
    return f"judge-unavailable-allow:{judgment.fallback_reason}"


def _log(
    settings: HookSettings,
    clock: Clock,
    observation: Observation,
    correction: Correction | None,
    decision: Decision,
    allow_reason: str,
) -> None:
    """One JSONL row per invocation, whether it corrected, allowed, or never judged."""
    judgment = observation.judgment
    candidate = observation.candidate
    JudgmentLog.in_state_dir(settings.state_dir).record(
        {
            "ts": clock.now_iso(),
            "event": observation.request.event_name,
            "session_id": observation.request.session_id,
            "decision": correction.decision if correction else "allow",
            "decision_kind": decision.kind.value,
            "allow_reason": allow_reason,
            "score": None if judgment is None else judgment.score,
            # Which bar the tool side applied: a host mutation is refused from the lower one.
            "destructive": observation.destructive,
            "thresholds": THRESHOLDS,
            "model": JUDGE_MODEL,
            "hop": HOP_NONE if judgment is None else judgment.hop,
            "latency_ms": None if judgment is None else judgment.duration_ms,
            "fallback_reason": "" if judgment is None else judgment.fallback_reason,
            "usage": None if judgment is None else judgment.usage,
            "task": _redact(_clip(observation.task, TASK_CHARS)),
            "candidate": ""
            if candidate is None
            else _redact(_clip(candidate.judged_text, CANDIDATE_CHARS)),
            "tool": "" if candidate is None else candidate.tool,
            "transcript_path": observation.request.transcript_path,
        }
    )


@dataclass(frozen=True, slots=True)
class JudgmentLog:
    """Append-only JSONL of every invocation; a write failure is never fatal.

    Never rotated, truncated or capped. This is the permanent record of what the guard
    decided and why, so history is kept rather than dropped: the file grows without bound
    and callers report its size instead of pruning it.
    """

    path: Path

    @classmethod
    def in_state_dir(cls, state_dir: Path) -> JudgmentLog:
        return cls(state_dir / JUDGMENTS_LOG_NAME)

    def record(self, entry: dict[str, Any]) -> None:
        with contextlib.suppress(OSError, TypeError, ValueError):
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry, sort_keys=True) + "\n")


def bypass_requested(env: Mapping[str, str]) -> bool:
    """``SCOPE_GUARD=off`` disables the guard, and is checked before anything else."""
    return env.get(BYPASS_ENV, "").strip().lower() == BYPASS_OFF


def _correction_cap(env: Mapping[str, str]) -> int:
    with contextlib.suppress(ValueError):
        value = int(env.get(CORRECTION_CAP_ENV, ""))
        if value > 0:
            return value
    return DEFAULT_CORRECTION_CAP


def _judge_timeout(env: Mapping[str, str]) -> float:
    with contextlib.suppress(ValueError):
        value = float(env.get(JUDGE_TIMEOUT_ENV, ""))
        if value > 0:
            return value
    return DEFAULT_JUDGE_TIMEOUT_SECS


def _score_of(reply: dict[str, Any]) -> float | None:
    answers = reply.get("answers")
    answer = answers.get(JUDGE_ANSWER_ID) if isinstance(answers, dict) else None
    if not isinstance(answer, dict) or answer.get("type") != QUESTION_KIND:
        return None
    score = answer.get(QUESTION_KIND)
    if isinstance(score, bool) or not isinstance(score, (int, float)):
        return None
    return float(score)


def _canonical_tool(name: str) -> str:
    """omp's spelling of a device tool, in the names the guard's rules match on.

    Built through ``HookEvent`` so the alias table stays the one owner of that mapping.
    """
    return HookEvent({"tool_name": name}).tool_name


def _device_args(content: Any) -> dict[str, Any]:
    """The arguments an omp ``write xd://<tool>`` carried: JSON text, or already decoded."""
    if isinstance(content, dict):
        return content
    if not isinstance(content, str) or not content.strip():
        return {}
    try:
        decoded = json.loads(content)
    except ValueError:
        return {}
    return decoded if isinstance(decoded, dict) else {}


def _is_lookup(tool: str) -> bool:
    """A tool whose last word is read/grep/glob/find/search/wait/list only looks."""
    last = re.split(r"[^a-z0-9]+", tool.lower())[-1]
    return last in LOOKUP_TOOL_SUFFIXES


def _file_path(tool_input: dict[str, Any]) -> str:
    """The path a Write/Edit-style tool would touch, if it names one."""
    for key in ("file_path", "path"):
        value = tool_input.get(key)
        if isinstance(value, str):
            return value
    return ""


# Programs that change machine state outside the repository and outside the user's task:
# signalling processes, controlling services, changing disks, mounts, the firewall or system
# security. This is the class the guard exists for — "host load is 400, so the agent starts
# dealing with load" — and it is decided from the parsed command, never from the judge,
# because real traffic scored a `pkill -f node` detour at 0.81 and a benign signed commit at
# 0.96: the score orders those two backwards, so no threshold can separate them.
HOST_MUTATING_PROGRAMS = {
    "kill": "terminates processes",
    "pkill": "terminates processes",
    "killall": "terminates processes",
    "launchctl": "controls services",
    "systemctl": "controls services",
    "service": "controls services",
    "diskutil": "changes disks",
    "hdiutil": "changes disks",
    "mount": "changes mounts",
    "umount": "changes mounts",
    "fsck": "changes the filesystem",
    "pfctl": "changes firewall rules",
    "socketfilterfw": "changes the firewall",
    "spctl": "changes the security policy",
    "csrutil": "changes system security",
    "scutil": "changes system configuration",
}
# Programs whose subcommands reach outside the repository. `mise run`, `git`, `rg` and every
# other program absent from both tables is never host-mutating, so its false positive is
# structurally impossible rather than merely unlikely.
HOST_MUTATING_SUBCOMMANDS = {
    "brew": (
        frozenset(
            {
                "install",
                "uninstall",
                "upgrade",
                "reinstall",
                "remove",
                "cleanup",
                "link",
                "unlink",
                "tap",
                "untap",
                "pin",
                "unpin",
                "services",
            }
        ),
        "changes installed packages or services",
    ),
    "pip": (frozenset({"install", "uninstall"}), "changes installed packages"),
    "pip3": (frozenset({"install", "uninstall"}), "changes installed packages"),
    "cargo": (frozenset({"install", "uninstall"}), "changes installed packages"),
    "gem": (
        frozenset({"install", "uninstall", "update"}),
        "changes installed packages",
    ),
    "go": (frozenset({"install"}), "changes installed packages"),
    "rustup": (
        frozenset(
            {
                "install",
                "uninstall",
                "update",
                "default",
                "component",
                "target",
                "toolchain",
            }
        ),
        "changes installed toolchains",
    ),
    "mise": (
        frozenset({"install", "uninstall", "upgrade", "use"}),
        "changes installed tools",
    ),
    "uv": (frozenset({"pip", "tool"}), "changes installed packages"),
    "defaults": (
        frozenset({"write", "delete", "import"}),
        "changes system configuration",
    ),
}
# A package manager is only host-mutating when the install is global: `npm install` fills the
# project's own node_modules, `npm i -g` replaces a tool on the machine.
GLOBAL_INSTALLERS = frozenset({"npm", "yarn", "pnpm", "bun"})
GLOBAL_INSTALL_SUBCOMMANDS = frozenset(
    {"install", "i", "add", "upgrade", "update", "remove", "uninstall", "rm", "link"}
)
GLOBAL_FLAGS = frozenset({"-g", "--global", "global"})
# Programs that write or destroy a path they are handed. Only a path outside the repository
# makes them host-mutating: `rm -rf build/` in the worktree is ordinary work.
FILE_MUTATING_PROGRAMS = frozenset(
    {
        "rm",
        "rmdir",
        "mv",
        "cp",
        "truncate",
        "dd",
        "chmod",
        "chown",
        "tee",
        "install",
        "ln",
        "rsync",
        "sed",
        "touch",
        "mkdir",
    }
)
SYSTEM_PATH_PREFIXES = (
    "/etc/",
    "/Library/",
    "/System/",
    "/usr/",
    "/bin/",
    "/sbin/",
    "/var/",
    "/private/",
    "/dev/",
    "/Applications/",
    "/opt/",
)
HOME = str(Path.home())


# A flag that asks a program to describe itself rather than do anything. Deliberately not
# `-h`/`-v`: on too many commands those mean dereference, verbose, or human-readable
# (`du -h`, `rm -v`, `cp -v`), so a mutating command carrying one would be skipped.
INFORMATIONAL_FLAGS = frozenset({"--help", "--version", "help", "version"})
# The reader commands a pipeline may end in, each with the flags that would let it run a
# program instead of reading. A reader carrying one of those is not informational. `xargs`
# (runs what it is handed), `sed` (`-i` writes), `tee` (writes), `sort` (`-o` writes) and
# `awk` (`system()`) are absent entirely, so `xargs kill` reaches the judge; so are `ps`,
# `ls`, `find`, `git` and `stat`, which inspect the host or the repo and are exactly the
# drift this guard exists for.
READERS_THAT_ONLY_READ = {
    "cat": (),
    "column": (),
    "cut": (),
    "fd": ("-x", "--exec", "-X", "--exec-batch"),
    "grep": (),
    "head": (),
    "jq": (),
    "less": (),
    "more": (),
    "rg": ("--pre", "--pre-glob"),
    "tail": (),
    "tr": (),
    "uniq": (),
    "wc": (),
}


def host_mutation_reason(action: str, file_path: str = "") -> str | None:
    """Why this candidate changes machine state outside the repository, or None.

    Deterministic and on the parsed command (``command_words`` for the simple commands,
    ``peel_command_prefixes`` for the wrappers that hand a command to another program),
    never a substring match. A deny needs this AND an off-task score, because the score
    alone cannot separate a process kill from a signed commit.
    """
    if _is_system_path(file_path):
        return "writes outside the repository"
    tokens = tokenize_with_fallback(strip_heredoc_bodies(action))
    if any(_is_system_path(target) for target in redirect_targets(tokens)):
        return "writes outside the repository"
    for argv in simple_commands(action):
        peeled, _ = peel_command_prefixes(argv)
        if not peeled:
            continue
        program, args = os.path.basename(peeled[0]), peeled[1:]
        reason = HOST_MUTATING_PROGRAMS.get(program)
        if reason is not None:
            return reason
        rule = HOST_MUTATING_SUBCOMMANDS.get(program)
        if rule is not None and args and args[0] in rule[0]:
            return rule[1]
        if program in GLOBAL_INSTALLERS and _installs_globally(args):
            return "changes installed packages"
        if program in FILE_MUTATING_PROGRAMS and any(
            _is_system_path(word) for word in args
        ):
            return "writes outside the repository"
    return None


def _installs_globally(args: list[str]) -> bool:
    """A global install: ``npm i -g``, ``yarn global add``, ``bun add -g``."""
    return any(word in GLOBAL_FLAGS for word in args) and any(
        word in GLOBAL_INSTALL_SUBCOMMANDS for word in args
    )


def _is_system_path(word: str) -> bool:
    """A path outside the repository: a system root, or the user's own Library."""
    if not word:
        return False
    text = word.strip().strip("'\"").replace("${HOME}", HOME).replace("$HOME", HOME)
    if text.startswith("~"):
        text = HOME + text[1:]
    normalized = os.path.normpath(text)
    return normalized.startswith(SYSTEM_PATH_PREFIXES) or normalized.startswith(
        f"{HOME}/Library/"
    )


def _is_informational(tool_input: dict[str, Any]) -> bool:
    """A command that only asks a program to describe itself, or only reads text.

    This is the live false positive that set the bar for the whole prefilter: `omp --help |
    head -50` — a read-only lookup feeding the goal in progress — was denied at 0.75 the
    first minute this guard ran. Every simple command must either carry a self-description
    flag or be a reader that is not carrying its own writing flag, so nothing skipped here
    can write a file or run a program. The parse is the house one (`command_words`), never a
    substring match.
    """
    command = tool_input.get("command")
    if not isinstance(command, str) or not command.strip():
        return False
    # A redirect can create or overwrite a file and a heredoc can execute, so neither is
    # purely informational. `2>&1` duplicates a stream rather than writing a file, hence the
    # `(?!&)`: `omp --help 2>&1 | head` still counts, `omp --help > notes.txt` does not.
    if re.search(r">>?(?!&)|<<", command):
        return False
    segments = simple_commands(command)
    if not segments:
        return False
    for argv in segments:
        if not argv:
            return False
        head = argv[0].rsplit("/", 1)[-1]
        writing_flags = READERS_THAT_ONLY_READ.get(head)
        if writing_flags is not None:
            if not any(word in writing_flags for word in argv[1:]):
                continue
        if any(word.lower() in INFORMATIONAL_FLAGS for word in argv[1:]):
            continue
        return False
    return True


def _candidate_of(request: ScopeRequest, runs: tuple[str, ...]) -> Candidate:
    """What the agent proposed, as the detector reads it.

    A proposed call is its command (or its whole input when the tool has no command); a
    finished turn is its closing message plus the calls the turn actually made.
    """
    if request.candidate_kind == CANDIDATE_TOOL:
        action = command_of(request.tool_input)
        if not action:
            action = json.dumps(request.tool_input, ensure_ascii=False, sort_keys=True)
        return Candidate(
            kind=CANDIDATE_TOOL,
            tool=request.tool,
            action=_clip(action, CANDIDATE_CHARS),
        )
    parts = [request.message.strip()] if request.message.strip() else []
    if runs:
        parts.append("Tool calls this turn:\n" + "\n".join(f"- {run}" for run in runs))
    return Candidate(
        kind=CANDIDATE_TURN,
        tool=request.tool,
        action=_clip("\n\n".join(parts), CANDIDATE_CHARS),
    )


def _runs_of(facts: Any) -> tuple[str, ...]:
    """The turn's own calls, newest last, clipped: the detector's ``recent_context``."""
    if facts is None:
        return ()
    runs = tuple(
        _clip(f"{run.tool}: {run.command}".strip(), RUN_CHARS)
        for run in facts.turn_runs
        if run.command
    )
    return runs[-RUNS_KEPT:]


def _trajectory_of(facts: Any) -> tuple[str, ...]:
    """What this request has already been through: earlier user turns, then the work done.

    The detector's ``recent_context``. One message in isolation cannot tell a fresh detour
    from the next step of work in progress, which is the false positive that made a signed
    commit on the task's own subject score as off-task.
    """
    if facts is None:
        return ()
    lines = [
        _clip(f"Earlier the user asked: {' '.join(prompt.text.split())}", TASK_CHARS)
        for prompt in facts.prompts[:-1][-PROMPTS_IN_CONTEXT:]
        if prompt.text.strip()
    ]
    for run in facts.turn_runs[-RESULTS_KEPT:]:
        outcome = "failed" if run.failed else "ok"
        detail = _clip(" ".join(run.output.split()), RESULT_CHARS) if run.output else ""
        lines.append(
            _clip(
                f"Ran {run.tool}: {run.command} -> {outcome}: {detail}",
                TRAJECTORY_CHARS,
            )
        )
    return tuple(lines)


def _task_of(facts: Any) -> str:
    """The most recent genuine user turn, which a later user redirect replaces."""
    if facts is None:
        return ""
    return _clip(facts.user_prompt.strip(), TASK_CHARS)


def _task_at(facts: Any) -> str:
    """When the user last spoke: the start of the request the correction cap bounds."""
    if facts is None or not facts.prompts:
        return ""
    return facts.prompts[-1].at


def _trivially_on_task(action: str, task: str) -> bool:
    """An exact command/word match, cheap and deliberately narrow.

    Skipping the judge here is the fail-open direction: it can only miss drift. The subset
    rule needs at least two significant words, so a one-word candidate (``rm parser.py``
    keeps only ``parser``) still reaches the detector.
    """
    if not action or not task:
        return False
    if action.strip().lower() in task.lower():
        return True
    words = _words(action)
    return len(words) >= MIN_WORDS_FOR_SUBSET_MATCH and words <= _words(task)


def _words(text: str) -> frozenset[str]:
    return frozenset(
        word for word in WORD.findall(text.lower()) if len(word) >= MIN_WORD_CHARS
    )


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _redact(text: str) -> str:
    return SECRET_ASSIGNMENT.sub(r"\1\2<redacted>", text)
