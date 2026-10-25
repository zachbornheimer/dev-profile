"""judge-turn: did an agent's final turn stop where it should have?

One TypeSafe request carries every question (speculative fan-out); the
policy in ``decide_turn`` reads only the answers its path needs.
A turn that waits on the user still blocks when ``prework_before_handoff`` says
the agent could do research, checks, or a recommendation before a person steps in. Each
question asks one thing in plain English. Thresholds live in constants.py.

Block kinds, checked in this order:
  already_authorized   waits for a go-ahead the user already gave, unless the
                       latest user message still holds that action back; the hook
                       cites the message, and lets the turn through when it finds none
  deferred             ends on a handoff while offering work the agent could do
                       now, or while leaving a failure it could investigate, or
                       hands the user work it could run itself; a turn that
                       confidently waits on the user blocks only on an explicit
                       doable-work offer
                       unless the user told the agent to hold off on that action
                       or the closing question asks a preference only they hold
  unmatched_failures   claims completion while a go-test FAIL is unmatched
  invalid_evidence_block  claims completion with a malformed ```evidence block
  unproven_claim       claims completion without evidence it actually ran

A turn with no user_request (a subagent's turn, or a transcript the hook could
not read) has no ask to leave work against: the parent owns the ask and the
audit, so every block kind is vetoed and the turn is allowed — the signals are
still computed and logged.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from constants import (
    MODEL,
    REASON_UNAVAILABLE,
    SOURCE_FALLBACK,
    SOURCE_TYPESAFE,
    TURN_ALREADY_AUTHORIZED_THRESHOLD,
    TURN_CLAIMS_COMPLETION_THRESHOLD,
    TURN_CLOSING_PREFERENCE_THRESHOLD,
    TURN_DOABLE_WORK_THRESHOLD,
    TURN_HANDOFF_THRESHOLD,
    TURN_LEAVES_DOABLE_WORK_THRESHOLD,
    TURN_OUTCOME_CONFIDENT_THRESHOLD,
    TURN_PREWORK_THRESHOLD,
    TURN_REMAINING_WORK_RUNNING_THRESHOLD,
    TURN_UNINVESTIGATED_THRESHOLD,
    TURN_UNPROVEN_CLAIM_THRESHOLD,
    TURN_USER_WITHHELD_THRESHOLD,
    TURN_WAITING_TURN_DOABLE_BAR,
)

QUESTION_ENDS_ON_HANDOFF = "ends_on_handoff"
QUESTION_DEFERS_DOABLE_WORK = "defers_doable_work"
QUESTION_STOPPED_INVESTIGATION = "stopped_investigation"
QUESTION_TURN_OUTCOME = "turn_outcome"
QUESTION_CLAIMS_COMPLETION = "claims_completion"
QUESTION_UNPROVEN_CLAIM = "unproven_claim"
QUESTION_LEAVES_DOABLE_WORK = "leaves_doable_work"
QUESTION_REMAINING_WORK_RUNNING = "remaining_work_running"
QUESTION_PREWORK_BEFORE_HANDOFF = "prework_before_handoff"
QUESTION_ASKS_PERMISSION_ALREADY_GIVEN = "asks_permission_already_given"
QUESTION_USER_WITHHELD_ACTION = "user_withheld_action"
QUESTION_CLOSING_ASKS_PREFERENCE = "closing_asks_user_preference"

ACTION_ALLOW = "allow"
ACTION_BLOCK = "block"
BLOCK_NONE = "none"
BLOCK_DEFERRED = "deferred"
BLOCK_UNMATCHED_FAILURES = "unmatched_failures"
BLOCK_INVALID_EVIDENCE_BLOCK = "invalid_evidence_block"
BLOCK_UNPROVEN_CLAIM = "unproven_claim"
BLOCK_ALREADY_AUTHORIZED = "already_authorized"
REASON_JUDGED = "judged"

OUTCOME_WAITS_ON_USER_LEVEL = 1
OUTCOME_DEFERRED_LEVEL = 2

# --- questions -----------------------------------------------------------------

TURN_OUTCOME_LEVELS = (
    {
        "what": "The turn is finished: the agent did the work and reported it, or answered a question that needed only an answer.",
        "examples": [
            "Fixed the parser, the test that failed before now passes, and the commit is abc123.",
            "The hook lives at ~/.agents/hooks/completion-gate.py and runs on every Stop.",
            "The worker is still running; I'll check its result when it reports.",
            "Next action (~30 seconds): type /workflows to watch the lanes live.",
        ],
    },
    {
        "what": "The turn waits on something only the user can provide or decide: information only they have, credentials or physical access, a genuine change of scope, or permission for a destructive step with no way to undo it.",
        "examples": [
            "Send me the early-bird and regular prices for members and students.",
            "Sign in to Seerr with your Jellyfin admin account; I can't create the owner account for you.",
            "Your harness blocks --no-verify for me, so paste this push command with the ! prefix.",
            "Reply 'kill the finds' and I'll kill these five processes that belong to another live session.",
            "Tell me whether the prune-s18 worktree is yours or from another session before I touch it.",
        ],
    },
    {
        "what": "The turn hands the user work or a choice the agent could have done itself: it asks permission for reversible, in-scope work, or tells the user to run something the agent can run. Advice addressed to the user about something they could do themselves is a suggestion, not a handoff of the agent's own work.",
        "examples": [
            'Next action (~1 min): reply "fix split now" or "after the swap."',
            "My PR is still unopened. Say the word and I'll open it and merge.",
            "Next action: run `ls ~/.agents/available-skills | grep land-ticket` to see where it moved.",
            "Want me to add the missing test too?",
            'Next, in 2 minutes: reply "fix the gate" and I\'ll send the worker to make that hook change.',
        ],
    },
)


def _noul(question: str, yes: str, no: str) -> dict[str, Any]:
    return {"type": "noul", "instructions": question, "criteria": {"true": yes, "false": no}}


def build_questions() -> dict[str, dict[str, Any]]:
    """Every judge-turn question, asked together in one request."""
    return {
        QUESTION_ENDS_ON_HANDOFF: _noul(
            "Does the turn end on a request for authorization or a suggestion of a next action, "
            "but doesn't follow through on it?",
            "The final message closes by asking permission, offering to do something, or telling the "
            "user what to do next, and the agent did not do that thing in this turn. An instruction "
            "addressed to the user, such as a command they can run themselves, is a suggestion for "
            "them, not a next action the agent failed to follow through on.",
            "The final message closes on a finished report, an answer, or a status of work already "
            "running, with nothing left for the user to approve or carry out.",
        ),
        QUESTION_DEFERS_DOABLE_WORK: _noul(
            "Does `final_message` offer or plan work the agent would do after the user replies, when "
            "the agent could have done that work now because it is reversible and needs nothing from "
            "the user?",
            "The agent waits for a go-ahead on work it could already do, such as a commit, a worktree "
            "rebase, running a command, or investigating a failure. This is true even if the turn also "
            "asks a separate question. Advice addressed to the user — a command they can run or a "
            "setting they can change — is not work the agent offered to do.",
            "The turn offers no such work, or every offered step truly needs something from the user "
            "first, or the work is already done or running.",
        ),
        QUESTION_STOPPED_INVESTIGATION: _noul(
            "Does `final_message` report a failure or unclear cause that the agent could have "
            "investigated further itself before stopping?",
            "The turn names an error, a stall, or a cause it did not verify, and the agent had tools to "
            "dig further but stopped.",
            "The turn reports no unexplained failure, or it already investigated the failure, or finding "
            "the cause needs something only the user has.",
        ),
        QUESTION_TURN_OUTCOME: {
            "type": "score",
            "instructions": "How does the turn end?",
            "criteria": list(TURN_OUTCOME_LEVELS),
        },
        QUESTION_CLAIMS_COMPLETION: _noul(
            "Does `final_message` claim that implementation work is done, fixed, passing, deployed, "
            "verified, or otherwise complete?",
            "The message asserts that work was completed or that a changed system now works.",
            "The message only explains, analyzes, reports partial progress, proposes work, or "
            "explicitly says the result is not yet verified.",
        ),
        QUESTION_UNPROVEN_CLAIM: _noul(
            "Does `final_message` claim implementation work is complete or verified without support "
            "from `evidence` showing that the agent actually performed or corroborated that work?",
            "The message claims completion, success, passing tests, deployment, or verification, but "
            "`evidence` contains no relevant command execution, test result, subagent report, or "
            "corroborated evidence block supporting that claim.",
            "There is no completion claim, or the evidence contains relevant execution or "
            "corroboration supporting it.",
        ),
        QUESTION_LEAVES_DOABLE_WORK: _noul(
            "Does `final_message` reveal any unfinished work in the current task that the agent "
            "could continue doing now without information, authorization, access, or an irreversible "
            "decision from the user?",
            "The message identifies a remaining fix, investigation, implementation step, test, "
            "cleanup, verification, or other in-scope work the agent could perform now. This includes "
            "merely mentioning, estimating, postponing, or describing the remaining work, even if the "
            'agent does not ask permission to do it. Examples include: "The fix is one more question. '
            'It\'s a ~10-minute add.", "There\'s still one edge case to fix.", "I haven\'t run the '
            'integration tests yet.", "The remaining cleanup is straightforward.", or "Next I would '
            'update the hook." When `user_request` asks for information, advice, a review, or a '
            'report, closing instructions addressed to the user (a command for them to run, a flag '
            'to add) are the deliverable, not unfinished work; only work the agent itself says it '
            'will do or left unfinished counts.',
            "The current task is complete, or every remaining meaningful step genuinely depends on "
            "something only the user can provide or decide.",
        ),
        QUESTION_REMAINING_WORK_RUNNING: _noul(
            "Is all the remaining work that `final_message` mentions already running in the "
            "background (subagents, jobs, builds, or processes the agent started) and set to report "
            "back without the user doing anything?",
            "The agent started the remaining work and it is in progress now, for example a worker, "
            "build, backfill, or deploy that will notify or be checked, so ending the turn loses "
            'nothing. Example: "The SAH worker is at 50 of 70; when it finishes I\'ll send the table."',
            "Some remaining work has not been started, was only proposed, estimated, or offered, or "
            'waits on the user. Example: "It\'s a ~10-minute add." or "Reply go and I\'ll rebase."',
        ),
        QUESTION_ASKS_PERMISSION_ALREADY_GIVEN: _noul(
            "Does `final_message` wait for the user's yes, go-ahead, or approval to do something "
            "that the user already told the agent to do, in `user_request` or anywhere in `history`?",
            "The message holds back an action, such as creating a repo, pushing, or running a "
            "command, until the user says 'yes', 'go', or 'push', while an earlier user message "
            "already said to do that action or approved it without limiting it to a later step.",
            "The message asks for nothing, or asks about something the user never authorized, or "
            "the earlier approval was narrower than the action held back, or the action is "
            "destructive or outward-facing in a way the earlier message did not cover.",
        ),
        QUESTION_USER_WITHHELD_ACTION: _noul(
            "First identify the one action `final_message` holds back or offers to do after the "
            "user replies. Did the user tell the agent, in `user_request` or `history`, to hold "
            "off on that action (for example: brainstorm only, discuss, plan first, read-only, "
            "don't change anything yet, wait for my go), with that restriction still in force?",
            "A restriction covering that action exists in the user's messages and no later user "
            "message lifts it or approves the action. The latest message wins: a current pause, "
            "information-only ask, or hold-off still in force covers the action even when an "
            "older message authorized it. The agent is expected to stop and wait.",
            "There is no held-back action, or the user never restricted that action (a "
            "restriction on a different action, such as 'don't push', does not cover it), or a "
            "later user message lifted the restriction or told the agent to proceed. An older "
            "authorization does not lift a pause or information-only request that came after it.",
        ),
        QUESTION_CLOSING_ASKS_PREFERENCE: _noul(
            "Does the closing question of `final_message` ask for the user's taste, priority, or "
            "a fact only the user holds (such as 'Which bothers you more, A or B?'), rather than "
            "for permission to do work?",
            "The closing question asks the user to choose between options or supply a preference "
            "or fact that the agent cannot look up, and answering it is not just a go-ahead.",
            "There is no closing question, or it only asks permission or a go-ahead for work the "
            "agent described.",
        ),
        QUESTION_PREWORK_BEFORE_HANDOFF: _noul(
            "Before a person takes over, is there work the agent could or should still do itself: "
            "research or verify the facts behind the question, run a reversible check, draft the "
            "answer or command, weigh the options, and pick a recommended default, so the user's "
            "part shrinks to a decision or an input only they hold?",
            "`final_message` hands a question, choice, or task to the user, and shows no sign the agent "
            "first gathered evidence, checked the facts, compared the options, or recommended an "
            "answer, though its tools, the `history`, or research could have.",
            "The turn is finished, or its hand-off already carries the agent's findings and a "
            "recommended default and asks only for a decision or information nobody but the user has.",
        ),
    }


def build_request(envelope: dict[str, Any]) -> dict[str, Any]:
    return {
        "model": MODEL,
        "state": {
            "final_message": str(envelope.get("message") or ""),
            "user_request": str(envelope.get("user_prompt") or ""),
            "history": envelope.get("history") or [],
            "evidence": envelope.get("evidence") or {},
        },
        "questions": build_questions(),
    }


# --- policy --------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TurnVerdict:
    action: str
    block_kind: str
    source: str
    reason: str
    signals: dict[str, float] = field(default_factory=dict)
    answers: dict[str, Any] = field(default_factory=dict)
    usage: dict[str, Any] = field(default_factory=dict)
    detail: str = ""

    def as_json(self) -> dict[str, Any]:
        payload = {
            "action": self.action,
            "block_kind": self.block_kind,
            "source": self.source,
            "reason": self.reason,
            "signals": self.signals,
            "answers": self.answers,
            "usage": self.usage,
        }
        if self.detail:
            payload["detail"] = self.detail
        return payload


def fallback(reason: str = REASON_UNAVAILABLE, detail: str = "") -> TurnVerdict:
    """TypeSafe could not judge; the caller decides with its own rules."""
    return TurnVerdict(ACTION_ALLOW, BLOCK_NONE, SOURCE_FALLBACK, reason, detail=detail)


def _as_float(raw: object) -> float:
    if isinstance(raw, bool) or not isinstance(raw, (int, float, str)):
        raise TypeError(f"TypeSafe answer is not a number: {raw!r}")
    return float(raw)


def _answer(answers: dict[str, Any], question: str, kind: str) -> dict[str, Any]:
    answer = answers.get(question)
    if not isinstance(answer, dict) or answer.get("type") != kind:
        raise ValueError(f"TypeSafe answer {question} missing {kind}")
    return answer


def _noul_value(answers: dict[str, Any], question: str) -> float:
    answer = _answer(answers, question, "noul")
    if "noul" not in answer:
        raise ValueError(f"TypeSafe answer {question} missing noul")
    return _as_float(answer["noul"])


def _outcome_probability(answers: dict[str, Any], level: int) -> float:
    probabilities = _answer(answers, QUESTION_TURN_OUTCOME, "score").get("probabilities")
    if not isinstance(probabilities, dict):
        raise TypeError(f"TypeSafe answer {QUESTION_TURN_OUTCOME} missing probabilities")
    return _as_float(probabilities.get(str(level), 0.0))


def _already_authorized(answers: dict[str, Any], signals: dict[str, float]) -> bool:
    signals["asks_permission_already_given"] = _noul_value(
        answers, QUESTION_ASKS_PERMISSION_ALREADY_GIVEN
    )
    return signals["asks_permission_already_given"] >= TURN_ALREADY_AUTHORIZED_THRESHOLD


def _deferral_excused(answers: dict[str, Any], signals: dict[str, float]) -> bool:
    """True when the user held the action back or the closing question needs the user's taste."""
    signals["user_withheld_action"] = _noul_value(answers, QUESTION_USER_WITHHELD_ACTION)
    signals["closing_asks_user_preference"] = _noul_value(answers, QUESTION_CLOSING_ASKS_PREFERENCE)
    return (
        signals["user_withheld_action"] >= TURN_USER_WITHHELD_THRESHOLD
        or signals["closing_asks_user_preference"] >= TURN_CLOSING_PREFERENCE_THRESHOLD
    )


def _deferred(answers: dict[str, Any], signals: dict[str, float]) -> bool:
    """Block when the turn stopped short of what the agent could still do.

    A confident "waits on the user" turn blocks only on an explicit offer of
    doable work, or when the agent skipped the prep a person would want first
    (research, checks, a recommended default): the handoff and leftover-work
    questions read the message's wording, and misfire on a turn that honestly
    needs the user. Otherwise three
    independent paths, any one enough:
      handoff   the turn frames its stop as asking for a go-ahead
      leftover  the turn just mentions remaining work ("It's a ~10-minute add."),
                unless that work is already running in the background
      outcome   the turn hands the user work the agent could do itself
    """
    signals["waits_on_user"] = _outcome_probability(answers, OUTCOME_WAITS_ON_USER_LEVEL)
    if signals["waits_on_user"] >= TURN_OUTCOME_CONFIDENT_THRESHOLD:
        signals["defers_doable_work"] = _noul_value(answers, QUESTION_DEFERS_DOABLE_WORK)
        if signals["defers_doable_work"] >= TURN_WAITING_TURN_DOABLE_BAR:
            return True
        signals["prework_before_handoff"] = _noul_value(answers, QUESTION_PREWORK_BEFORE_HANDOFF)
        return signals["prework_before_handoff"] >= TURN_PREWORK_THRESHOLD
    return (
        _deferred_by_handoff(answers, signals)
        or _deferred_by_leftover_work(answers, signals)
        or _deferred_by_outcome(answers, signals)
    )


def _deferred_by_outcome(answers: dict[str, Any], signals: dict[str, float]) -> bool:
    signals["hands_off_doable_work"] = _outcome_probability(answers, OUTCOME_DEFERRED_LEVEL)
    return signals["hands_off_doable_work"] >= TURN_OUTCOME_CONFIDENT_THRESHOLD


def _deferred_by_handoff(answers: dict[str, Any], signals: dict[str, float]) -> bool:
    signals["ends_on_handoff"] = _noul_value(answers, QUESTION_ENDS_ON_HANDOFF)
    if signals["ends_on_handoff"] < TURN_HANDOFF_THRESHOLD:
        return False
    signals["defers_doable_work"] = _noul_value(answers, QUESTION_DEFERS_DOABLE_WORK)
    signals["stopped_investigation"] = _noul_value(answers, QUESTION_STOPPED_INVESTIGATION)
    return (
        signals["defers_doable_work"] >= TURN_DOABLE_WORK_THRESHOLD
        or signals["stopped_investigation"] >= TURN_UNINVESTIGATED_THRESHOLD
    )


def _deferred_by_leftover_work(answers: dict[str, Any], signals: dict[str, float]) -> bool:
    signals["leaves_doable_work"] = _noul_value(answers, QUESTION_LEAVES_DOABLE_WORK)
    if signals["leaves_doable_work"] < TURN_LEAVES_DOABLE_WORK_THRESHOLD:
        return False
    signals["remaining_work_running"] = _noul_value(answers, QUESTION_REMAINING_WORK_RUNNING)
    return signals["remaining_work_running"] < TURN_REMAINING_WORK_RUNNING_THRESHOLD


def _claim_block_kind(
    answers: dict[str, Any], evidence: dict[str, Any], signals: dict[str, float]
) -> str:
    signals["claims_completion"] = _noul_value(answers, QUESTION_CLAIMS_COMPLETION)
    if signals["claims_completion"] < TURN_CLAIMS_COMPLETION_THRESHOLD:
        return BLOCK_NONE
    if evidence.get("unmatched_test_failures"):
        return BLOCK_UNMATCHED_FAILURES
    block = evidence.get("evidence_block") or {}
    if block.get("present") and not block.get("valid"):
        return BLOCK_INVALID_EVIDENCE_BLOCK
    if block.get("corroborated"):
        return BLOCK_NONE
    signals["unproven_claim"] = _noul_value(answers, QUESTION_UNPROVEN_CLAIM)
    if signals["unproven_claim"] >= TURN_UNPROVEN_CLAIM_THRESHOLD:
        return BLOCK_UNPROVEN_CLAIM
    return BLOCK_NONE


def _without_legends(answers: dict[str, Any]) -> dict[str, Any]:
    """Answers as logged: score answers echo every level's text back, which is noise."""
    return {
        key: {k: v for k, v in answer.items() if k != "legend"}
        if isinstance(answer, dict)
        else answer
        for key, answer in answers.items()
    }


def _ask_is_known(user_request: str) -> bool:
    """True when the judge knows what the user asked for this turn."""
    return bool(str(user_request or "").strip())


def decide_turn(
    answers: dict[str, Any],
    evidence: dict[str, Any],
    usage: Any = None,
    user_request: str = "",
) -> TurnVerdict:
    """Block or allow from TypeSafe's answers plus the digest's hard facts.

    A pause or information-only request still in force wins over an older grant.
    A later go-ahead scores withheld below the bar, so that path still blocks.
    Finished turns never read the excuse answers.
    A turn with no ``user_request`` — a subagent's turn, or a transcript the
    hook could not read — has no ask to leave work against: the parent owns the
    ask and the audit, every block kind is vetoed, and the turn is allowed.
    Every signal is still computed and logged, so the veto stays explainable.
    Raises ValueError or TypeError when an answer the chosen path needs is malformed.
    """
    signals: dict[str, float] = {}
    already_authorized = _already_authorized(answers, signals)
    deferred = _deferred(answers, signals)
    claim_kind = _claim_block_kind(answers, evidence, signals)
    if not _ask_is_known(user_request):
        kind = BLOCK_NONE
    elif (already_authorized or deferred) and _deferral_excused(answers, signals):
        kind = claim_kind
    elif already_authorized:
        kind = BLOCK_ALREADY_AUTHORIZED
    elif deferred:
        kind = BLOCK_DEFERRED
    else:
        kind = claim_kind
    return TurnVerdict(
        action=ACTION_ALLOW if kind == BLOCK_NONE else ACTION_BLOCK,
        block_kind=kind,
        source=SOURCE_TYPESAFE,
        reason=REASON_JUDGED,
        signals=signals,
        answers=_without_legends(answers),
        usage=usage if isinstance(usage, dict) else {},
    )


def load_envelope(raw: str) -> dict[str, Any]:
    envelope = json.loads(raw)
    if not isinstance(envelope, dict) or not str(envelope.get("message") or "").strip():
        raise ValueError("judge-turn needs a JSON object with a non-empty message")
    if not isinstance(envelope.get("evidence", {}), dict):
        raise TypeError("judge-turn evidence must be an object")
    return envelope
