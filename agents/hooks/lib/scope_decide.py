"""Scope-guard hook integration: one policy for PreToolUse and Stop.

The model identifies likely detours. Deterministic explicit prohibitions prevent
known forbidden commands; independent model signals reduce false positives.
This is a new policy and must be calibrated on real traces before relying on it.

Fail-open cases: missing transcript/task, missing judge CLI, invalid response,
timeout, configured bypass, or an exhausted intervention budget. Explicit
user-command prohibitions remain in force during those failures.
"""

from __future__ import annotations

import contextlib
import json
import math
import os
import re
import subprocess
import sys
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from completion_gate_session_state import RejectLedger
from completion_gate_transcript import read_transcript_facts
from completion_gate_transcript_events import command_of
from hook_common import Clock, Decision, HookEvent, HookSettings, sha256_digest
from scope_guard_rules import (
    evaluate_stop,
    evaluate_tool,
    is_read_only_probe,
    prohibited_full_ci,
)
from typesafe_location import TYPESAFE_CLI

HOOK_NAME = "scope-guard"
QUESTION_FILE = Path(__file__).resolve().parents[1] / "scope-guard.yaml"
TOOL_QUESTIONS = ("OffTopic", "UnnecessaryWork", "execute_proposed_call")
STOP_QUESTIONS = ("OffTopic", "UnnecessaryWork")
JUDGE_CLI_ENV = "HC_SCOPE_JUDGE_CLI"
JUDGE_TIMEOUT_ENV = "HC_SCOPE_JUDGE_TIMEOUT_SECS"
BYPASS_ENV = "SCOPE_GUARD"
CAP_ENV = "SCOPE_GUARD_CAP"
DEFAULT_TIMEOUT_SECS = 6.0
DEFAULT_CAP = 8
JUDGMENTS_LOG = "scope-judgments.jsonl"
CORRECTIONS_LEDGER = "scope-corrections-{session}.tsv"
TASK_ATTRIBUTIONS = frozenset({"user", "agent"})
PROMPTS_KEPT = 8
RUNS_KEPT = 8
TASK_CHARS = 1200
CANDIDATE_CHARS = 2400
CONTEXT_CHARS = 400
LOG_CHARS = 400

SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b(token|secret|password|passwd|api[_-]?key|access[_-]?key|authorization)"
    r"(\s*[:=]\s*)([^\s,;]+)"
)


def _redact(text: str) -> str:
    """Mask obvious credentials before remote judgment and local logging."""
    return SECRET_ASSIGNMENT.sub(r"\1\2<redacted>", text)


def _clip(text: str, limit: int) -> str:
    """Retain both ends: commands often hide a second operation after `&&`."""
    if len(text) <= limit:
        return text
    head = (limit - 1) // 2
    return text[:head] + "…" + text[-(limit - head - 1) :]


def _event_field(event: HookEvent, *names: str) -> str:
    value = event.field(*names)
    return value if isinstance(value, str) else ""


@dataclass(frozen=True, slots=True)
class ScopeRequest:
    """Canonical representation of an intercepted agent event."""

    event_name: str
    session_id: str
    transcript_path: str
    tool: str
    tool_input: dict[str, Any]
    final_message: str
    stop_hook_active: bool

    @property
    def kind(self) -> str | None:
        return {"PreToolUse": "tool", "Stop": "conversation"}.get(self.event_name)

    @classmethod
    def from_event(cls, event: HookEvent) -> ScopeRequest:
        # OMP tunnels tool calls through `write xd://<name>`.
        tool = event.tool_name
        args = event.tool_input_section()
        if event.raw_tool_name in {"write", "Write"}:
            path = args.get("path")
            if isinstance(path, str) and path.startswith("xd://"):
                tool = HookEvent({"tool_name": path[5:]}).tool_name
                data = args.get("content")
                if isinstance(data, dict):
                    args = data
                elif isinstance(data, str):
                    with contextlib.suppress(ValueError):
                        decoded = json.loads(data)
                        if isinstance(decoded, dict):
                            args = decoded
        return cls(
            event_name=event.event_name,
            session_id=event.session_id,
            transcript_path=_event_field(event, "transcript_path", "transcriptPath"),
            tool=tool,
            tool_input=args,
            final_message=_event_field(
                event, "last_assistant_message", "lastAssistantMessage"
            ),
            stop_hook_active=bool(
                event.payload.get("stop_hook_active") is True
                or event.payload.get("stopHookActive") is True
            ),
        )


@dataclass(frozen=True, slots=True)
class ScopeJudgment:
    """Results from the selected questions, or a fail-open reason."""

    scores: dict[str, float] = field(default_factory=dict)
    fallback_reason: str = ""
    duration_ms: float = 0.0
    usage: dict[str, Any] | None = None
    hop: str = "unknown"


@dataclass(frozen=True, slots=True)
class Observation:
    """All facts for one event; collection is separate from enforcement."""

    request: ScopeRequest
    task: str = ""
    candidate: str = ""
    since_iso: str = ""
    candidate_hash: str = ""
    skip: str = ""
    forced_reason: str = ""
    judgment: ScopeJudgment | None = None


@dataclass(frozen=True, slots=True)
class Correction:
    """A planned intervention and the concrete reason shown to the agent."""

    decision: str
    reason: str
    source: str


def load_questions(path: Path = QUESTION_FILE) -> dict[str, dict[str, Any]]:
    """Validate YAML and preserve the Jev noul question contract."""
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise TypeError("Scope question file is not a mapping")
    results: dict[str, dict[str, Any]] = {}
    for name, raw in loaded.items():
        if not isinstance(raw, dict) or not isinstance(raw.get("instructions"), str):
            raise TypeError(f"Invalid question: {name}")
        criteria = raw.get("criteria")
        if not isinstance(criteria, dict):
            raise TypeError(f"Missing criteria: {name}")
        normalized = {str(k).lower(): str(v) for k, v in criteria.items()}
        if not normalized.get("true") or not normalized.get("false"):
            raise ValueError(f"Missing boolean criterion: {name}")
        results[str(name)] = {
            "type": "noul",
            "instructions": raw["instructions"],
            "criteria": {"true": normalized["true"], "false": normalized["false"]},
        }
    for name in (*TOOL_QUESTIONS, *STOP_QUESTIONS):
        if name not in results:
            raise ValueError(f"Missing runtime question: {name}")
    return results


def load_question(path: Path = QUESTION_FILE) -> dict[str, Any]:
    """Backward-compatible accessor for the original OffTopic question."""
    return load_questions(path)["OffTopic"]


DIRECTIVES_FILE = Path(__file__).resolve().parents[1] / "scope-guard-directives.yaml"
DIRECTIVES_ENV = "HC_SCOPE_DIRECTIVES_FILE"
DIRECTIVE_CHARS = 400


def _applicable_directives(env: Mapping[str, str] | None = None) -> list[str]:
    """Standing directives the judge sees, from one YAML file the harness owns.

    ``applicable_directives`` was hardcoded empty: the guard had no source for
    the harness's standing rules, so the judge never saw them (the 2026-10-30
    review, chain 3). The file holds one directive per list entry; a missing
    file keeps the old empty behavior.
    """
    path = Path((env or os.environ).get(DIRECTIVES_ENV, DIRECTIVES_FILE))
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError:
        return []
    if not isinstance(loaded, Mapping):
        return []
    directives = loaded.get("directives")
    if not isinstance(directives, list):
        return []
    return [
        _clip(str(item).strip(), DIRECTIVE_CHARS)
        for item in directives
        if str(item).strip()
    ]


def judge_request(
    task: str,
    candidate: str,
    kind: str,
    context: tuple[str, ...],
    specs: dict[str, dict[str, Any]],
    names: tuple[str, ...],
) -> dict[str, Any]:
    """Send multiple related questions about the exact same candidate state."""
    return {
        "conversation": _redact(task),
        "context": {
            "user_request": _redact(task),
            "applicable_directives": _applicable_directives(),
            "recent_context": [_redact(line) for line in context],
            "candidate_event": {"kind": kind, "content": _redact(candidate)},
        },
        "questions": [specs[name] for name in names],
    }


def _timeout(env: Mapping[str, str]) -> float:
    try:
        value = float(env.get(JUDGE_TIMEOUT_ENV, str(DEFAULT_TIMEOUT_SECS)))
        return value if math.isfinite(value) and value > 0 else DEFAULT_TIMEOUT_SECS
    except ValueError:
        return DEFAULT_TIMEOUT_SECS


@dataclass(frozen=True, slots=True)
class ScopeJudge:
    """Invoke the existing typesafe interrogate CLI; never throw on model failure."""

    cli: Path
    timeout_secs: float
    specs: dict[str, dict[str, Any]]

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> ScopeJudge:
        return cls(
            cli=Path(env.get(JUDGE_CLI_ENV) or TYPESAFE_CLI),
            timeout_secs=_timeout(env),
            specs=load_questions(),
        )

    def judge(
        self,
        task: str,
        candidate: str,
        kind: str,
        context: tuple[str, ...],
    ) -> ScopeJudgment:
        if not self.cli.is_file():
            return ScopeJudgment(fallback_reason="judge-cli-missing")
        names = TOOL_QUESTIONS if kind == "tool" else STOP_QUESTIONS
        started = time.monotonic()
        try:
            done = subprocess.run(
                [sys.executable, str(self.cli), "interrogate", "--json"],
                input=json.dumps(
                    judge_request(task, candidate, kind, context, self.specs, names)
                ),
                capture_output=True,
                text=True,
                timeout=self.timeout_secs,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return ScopeJudgment(fallback_reason="judge-timeout")
        except OSError as exc:
            return ScopeJudgment(
                fallback_reason=f"judge-cli-error:{type(exc).__name__}"
            )
        elapsed = round((time.monotonic() - started) * 1000, 1)
        if done.returncode != 0:
            return ScopeJudgment(
                fallback_reason=f"judge-exit-{done.returncode}", duration_ms=elapsed
            )
        try:
            reply = json.loads(done.stdout)
        except ValueError:
            return ScopeJudgment(fallback_reason="judge-not-json", duration_ms=elapsed)
        if not isinstance(reply, dict) or reply.get("source") != "typesafe":
            return ScopeJudgment(
                fallback_reason="judge-source-unavailable", duration_ms=elapsed
            )
        answers = reply.get("answers")
        if not isinstance(answers, dict):
            return ScopeJudgment(
                fallback_reason="judge-answers-missing", duration_ms=elapsed
            )
        scores: dict[str, float] = {}
        for index, name in enumerate(names, start=1):
            answer = answers.get(f"question_{index}")
            if not isinstance(answer, dict) or answer.get("type") != "noul":
                return ScopeJudgment(
                    fallback_reason=f"judge-answer-{name}-missing", duration_ms=elapsed
                )
            value = answer.get("noul")
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                return ScopeJudgment(
                    fallback_reason=f"judge-answer-{name}-invalid", duration_ms=elapsed
                )
            score = float(value)
            if not math.isfinite(score) or score < 0 or score > 1:
                return ScopeJudgment(
                    fallback_reason=f"judge-answer-{name}-range", duration_ms=elapsed
                )
            scores[name] = score
        return ScopeJudgment(
            scores=scores,
            duration_ms=elapsed,
            usage=reply.get("usage") if isinstance(reply.get("usage"), dict) else None,
            hop="typesafe",
        )


def _candidate(request: ScopeRequest) -> str:
    """Capture the proposed command or finished message, never just tool names."""
    if request.kind == "conversation":
        return _clip(request.final_message.strip(), CANDIDATE_CHARS)
    command = command_of(request.tool_input)
    if not command:
        command = json.dumps(request.tool_input, ensure_ascii=False, sort_keys=True)
    return _clip(f"{request.tool}: {command}", CANDIDATE_CHARS)


def _is_execution_tool(tool: str) -> bool:
    """Avoid treating prose in a file write as a shell command."""
    return bool(
        re.search(
            r"(?:^|[^a-z0-9])(?:bash|shell|exec|eval|run_command|terminal|command)(?:$|[^a-z0-9])",
            tool.lower(),
        )
    ) or tool.lower().endswith("run_command")


def _execution_text(request: ScopeRequest) -> str:
    """Use the untruncated executable input for deterministic prohibitions."""
    if not _is_execution_tool(request.tool):
        return ""
    command = command_of(request.tool_input)
    if command:
        return command
    # Some command dispatchers wrap the invocation in a code/eval field.
    value = request.tool_input.get("code")
    return value if isinstance(value, str) else ""


def _transcript_disposed_on_disk(path: str) -> bool:
    """True when the on-disk JSONL ends at an earlier run's session_exit (e.g. resumed on SQL)."""
    if not path:
        return False
    try:
        with Path(path).open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - 2048), os.SEEK_SET)
            lines = handle.read().decode("utf-8", errors="ignore").strip().splitlines()
            return bool(lines and '"customType":"session_exit"' in lines[-1])
    except OSError:
        return False


def _prompts(facts: Any) -> tuple[str, ...]:
    if facts is None:
        return ()
    return tuple(item.text.strip() for item in facts.prompts if item.text.strip())


TASK_PROMPTS = 3


def _task_of(facts: Any) -> str:
    """The recent asks, oldest first, so a bare path still carries its request.

    ``facts.user_prompt`` is only the newest message. Measured on the live guard:
    when that message was ``/private/tmp/Downloads/scope-guard-dropin.zip`` the
    judge scored a real ``pkill`` detour OffTopic 0.68 / UnnecessaryWork 0.83 and
    allowed it; the identical candidate against a real request scored
    0.94 / 0.96 / 0.03 and denied. The bar was never the problem — the task it
    was measured against named no work. The last few asks give the judge the
    conversation that message belongs to.
    """
    prompts = _prompts(facts)[-TASK_PROMPTS:]
    if not prompts:
        return ""
    return _clip("\n".join(prompts), TASK_CHARS)


CAPABILITY_CLI_ENV = "HC_CAPABILITY_CLI"
CAPABILITY_TURNS = 3
CAPABILITY_TIMEOUT_SECS = 3.0
# Hooks run with a PATH that carries neither `node` nor `bun`, so the CLI's
# `#!/usr/bin/env node` shebang exits 127 there. The interpreter is resolved here
# and its directory put on the child's PATH. bun is tried first: it starts in tens
# of milliseconds, where node costs roughly a second on every tool call.
CAPABILITY_RUNNERS = (
    ".local/share/mise/installs/bun/*/bin/bun",
    ".local/share/mise/installs/node/*/bin/node",
)


def _newest_runner(pattern: str) -> Path | None:
    found = sorted(path for path in Path.home().glob(pattern) if path.is_file())
    return found[-1] if found else None


def _recent_turns(session_id: str, env: Mapping[str, str]) -> tuple[str, ...]:
    """The session's newest turns, as the harness reports them.

    The transcript reader yields the user's asks and the tool calls, but not what
    the agent itself has been saying. The judge needs that to tell "continuing the
    work" from "started something else". A missing CLI, a missing interpreter, a
    timeout or a malformed reply returns nothing — the guard then falls back to the
    transcript, never to a guess.
    """
    override = env.get(CAPABILITY_CLI_ENV, "").strip()
    cli = (
        Path(override) if override else Path.home() / ".local/share/aube/bin/capability"
    )
    if not cli.is_file() or not session_id:
        return ()
    runner = next(
        (found for pattern in CAPABILITY_RUNNERS if (found := _newest_runner(pattern))),
        None,
    )
    if runner is None:
        return ()
    payload = json.dumps(
        {"conversation": f"omp:{session_id}", "turns": CAPABILITY_TURNS}
    )
    child_env = dict(os.environ)
    child_env["PATH"] = f"{runner.parent}:{child_env.get('PATH', '/usr/bin:/bin')}"
    try:
        done = subprocess.run(
            [str(runner), str(cli), "run", "get_recent_turns", "--input", payload],
            capture_output=True,
            text=True,
            timeout=CAPABILITY_TIMEOUT_SECS,
            check=False,
            env=child_env,
        )
    except (subprocess.SubprocessError, OSError):
        return ()
    if done.returncode != 0:
        return ()
    try:
        reply = json.loads(done.stdout)
    except ValueError:
        return ()
    if not isinstance(reply, dict):
        return ()
    lines = []
    for turn in (reply.get("turns") or [])[-CAPABILITY_TURNS:]:
        if not isinstance(turn, dict):
            continue
        for message in turn.get("messages") or []:
            if not isinstance(message, dict):
                continue
            speaker = str(message.get("from") or "").strip()
            text = " ".join(str(message.get("content") or "").split())
            if speaker and text:
                lines.append(
                    _clip(
                        f"Earlier in this session, {speaker} said: {text}",
                        CONTEXT_CHARS,
                    )
                )
    return tuple(lines)


def _context(facts: Any) -> tuple[str, ...]:
    """Make relevant prior instructions and the current trajectory visible to Jev."""
    if facts is None:
        return ()
    prior = [
        "Earlier task message: " + _clip(text, CONTEXT_CHARS)
        for text in _prompts(facts)[:-1][-PROMPTS_KEPT:]
    ]
    recent = []
    for run in facts.turn_runs[-RUNS_KEPT:]:
        command = str(run.command or "")
        outcome = "failed" if run.failed else "ok"
        output = _clip(" ".join((run.output or "").split()), 120)
        recent.append(
            "Prior tool call: "
            + _clip(f"{run.tool}: {command} -> {outcome}: {output}", CONTEXT_CHARS)
        )
    return tuple(prior + recent)


def _cap(env: Mapping[str, str]) -> int:
    try:
        value = int(env.get(CAP_ENV, str(DEFAULT_CAP)))
        return value if value > 0 else DEFAULT_CAP
    except ValueError:
        return DEFAULT_CAP


def _ledger(settings: HookSettings, session: str) -> RejectLedger | None:
    if not session:
        return None
    return RejectLedger(settings.state_dir / CORRECTIONS_LEDGER.format(session=session))


def _observe(
    request: ScopeRequest,
    ledger: RejectLedger | None,
    env: Mapping[str, str],
) -> Observation:
    """Gather state; enforce explicit user constraints before consulting Jev."""
    if env.get(BYPASS_ENV, "").strip().lower() == "off":
        return Observation(request, skip="guard-disabled")
    if request.kind is None:
        return Observation(request, skip="unsupported-event")
    if request.kind == "conversation" and request.stop_hook_active:
        return Observation(request, skip="recursive-stop")
    if not request.session_id:
        return Observation(request, skip="no-session-id")
    candidate = _candidate(request)
    if not candidate:
        return Observation(request, skip="empty-candidate")
    # Read-only probes can never mutate state; judging them only burns model
    # calls and risks denying legitimate `--help`/presence checks.
    if request.kind == "tool":
        execution_text = _execution_text(request)
        if execution_text and is_read_only_probe(execution_text):
            return Observation(request, candidate=candidate, skip="read-only-probe")
    facts = (
        read_transcript_facts(request.transcript_path, TASK_ATTRIBUTIONS)
        if request.transcript_path
        and not _transcript_disposed_on_disk(request.transcript_path)
        else None
    )
    task = _task_of(facts)
    if not task:
        return Observation(request, candidate=candidate, skip="no-user-task")
    task = _clip(task, TASK_CHARS)
    since_iso = str(facts.prompts[-1].at or "") if facts.prompts else ""
    digest = sha256_digest(
        f"{request.session_id}:{since_iso}:{request.kind}:{candidate}"
    )
    Observation(
        request=request,
        task=task,
        candidate=candidate,
        since_iso=since_iso,
        candidate_hash=digest,
    )

    # This explicit prohibition is enforced even if Jev fails, has timed out, or
    # the correction budget is exhausted. Only actual task messages count.
    if request.kind == "tool" and prohibited_full_ci(
        _execution_text(request), _prompts(facts)
    ):
        return Observation(
            request=request,
            task=task,
            candidate=candidate,
            since_iso=since_iso,
            candidate_hash=digest,
            forced_reason="User explicitly prohibited `mise run ci`.",
        )

    # Never allow a previously denied proposed call solely because its text has
    # already been seen. Repeat tool calls must receive the same refusal.
    if ledger is not None and ledger.hash_seen(digest):
        if request.kind == "tool":
            return Observation(
                request=request,
                task=task,
                candidate=candidate,
                since_iso=since_iso,
                candidate_hash=digest,
                forced_reason="This exact tool call was already denied for this request.",
            )
        return Observation(
            request, task, candidate, since_iso, digest, skip="repeated-stop"
        )

    if ledger is not None and since_iso and ledger.count(since_iso) >= _cap(env):
        return Observation(
            request=request,
            task=task,
            candidate=candidate,
            since_iso=since_iso,
            candidate_hash=digest,
            skip="correction-cap-reached",
        )

    try:
        # The harness's recent turns first, then the transcript's asks and tool
        # runs: the historical state plus this call, which is what the judge needs.
        context = _recent_turns(request.session_id, env) + _context(facts)
        judgment = ScopeJudge.from_env(env).judge(
            task, candidate, request.kind, context
        )
    except (OSError, TypeError, ValueError, yaml.YAMLError) as exc:
        return Observation(
            request=request,
            task=task,
            candidate=candidate,
            since_iso=since_iso,
            candidate_hash=digest,
            skip=f"judge-setup-failure:{type(exc).__name__}",
        )
    return Observation(request, task, candidate, since_iso, digest, judgment=judgment)


def _plan(observation: Observation) -> Correction | None:
    """Turn one verdict into actionable feedback, with no system mutations."""
    if observation.skip:
        return None
    request = observation.request
    source = "explicit-constraint" if observation.forced_reason else "model"
    if observation.forced_reason:
        reason = observation.forced_reason
    else:
        if observation.judgment is None or observation.judgment.fallback_reason:
            return None
        scores = observation.judgment.scores
        outcome = (
            evaluate_tool(scores) if request.kind == "tool" else evaluate_stop(scores)
        )
        if not outcome.deny:
            return None
        reason = outcome.reason

    if request.kind == "tool":
        details = (
            "Scope guard: DO NOT execute that proposed tool call.\n"
            f"Current task: {observation.task}\n"
            f"Rejected call: {_clip(observation.candidate, 400)}\n"
            f"Reason: {reason}.\n"
            "Return to the user's request. Use only the smallest necessary next action; "
            "do not replace this detour with another CPU, disk, or CI investigation. "
            "If verification is unnecessary, answer with the evidence available."
        )
        return Correction("off-task-tool-call", details, source)
    details = (
        "Scope guard: the assistant ended off-task.\n"
        f"Current task: {observation.task}\n"
        f"Reason: {reason}.\n"
        "Finish the requested work and provide the result. Do not continue an "
        "incidental investigation; ask only for information unavailable to the agent."
    )
    return Correction("off-task-turn-end", details, source)


def _write_log(
    settings: HookSettings,
    clock: Clock,
    observation: Observation,
    correction: Correction | None,
    decision: Decision,
) -> None:
    """Audit each event without allowing a log failure to stop agent work."""
    judgment = observation.judgment
    record = {
        "ts": clock.now_iso(),
        "event": observation.request.event_name,
        "session_id": observation.request.session_id,
        "decision": correction.decision if correction else "allow",
        "decision_kind": decision.kind.value,
        "source": correction.source if correction else "",
        "reason": observation.skip or (judgment.fallback_reason if judgment else ""),
        "scores": judgment.scores if judgment else {},
        "duration_ms": judgment.duration_ms if judgment else None,
        "hop": judgment.hop if judgment else "none",
        "usage": judgment.usage if judgment else None,
        "task": _redact(_clip(observation.task, LOG_CHARS)),
        "candidate": _redact(_clip(observation.candidate, LOG_CHARS)),
    }
    with contextlib.suppress(OSError, TypeError, ValueError):
        target = settings.state_dir / JUDGMENTS_LOG
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")


def scope_decision(
    event: HookEvent, *, env: Mapping[str, str] | None = None
) -> Decision:
    """Entrypoint for either hook; emits a decision immediately in this turn."""
    environment = os.environ if env is None else env
    request = ScopeRequest.from_event(event)
    settings = HookSettings.from_env(environment)
    clock = Clock.from_env(environment)
    ledger = _ledger(settings, request.session_id)
    observation = _observe(request, ledger, environment)
    correction = _plan(observation)
    if correction is None:
        decision = Decision.no_objection(
            observation.skip
            or (
                observation.judgment.fallback_reason
                if observation.judgment
                else "allow"
            )
        )
    else:
        # Repeated forbidden calls remain denied without using up the model budget.
        if ledger is not None and not ledger.hash_seen(observation.candidate_hash):
            with contextlib.suppress(OSError, ValueError):
                ledger.record(clock.now_iso(), observation.candidate_hash)
        if request.kind == "tool":
            decision = Decision.deny(correction.reason, log_detail=correction.decision)
        else:
            decision = Decision.block(correction.reason)
    _write_log(settings, clock, observation, correction, decision)
    return decision
