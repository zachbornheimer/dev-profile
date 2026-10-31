"""Pure, testable policy for scope-guard.

Jev scores are *signals*, not calibrated probabilities of correctness. The
thresholds are conservative starting values and need evaluation on your cases.
This module has no dependencies on the hook runtime.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

# An explicit user prohibition is enforced without a model call. This narrow rule
# intentionally does not attempt to parse arbitrary natural-language prohibitions.
FULL_CI_CALL = re.compile(r"(?<![\w-])mise\s+run\s+ci\b", re.IGNORECASE)
FULL_CI_NEGATIVE = re.compile(
    r"\b(?:don't|do\s+not|never|must\s+not|no)\s+"
    r"(?:(?:please\s+)?run\s+)?(?:mise\s+run\s+ci|full\s+ci)\b",
    re.IGNORECASE,
)
FULL_CI_POSITIVE = re.compile(
    r"\b(?:please\s+)?(?:run|execute)\s+"
    r"(?:mise\s+run\s+ci|full\s+ci)\b",
    re.IGNORECASE,
)

# A read-only probe can never mutate state, so judging it wastes a model call and
# invites false denials of legitimate help/version/presence checks
# (`wt switch --help` was denied in omp_01a18dd0).
READ_ONLY_PROBE = re.compile(
    r"(?:^|[\s;&|])(?:"
    r"--help(?![\w-])|-h\b"
    r"|--version(?![\w-])|-V\b"
    r"|command\s+-v\b"
    r"|command\s+-p\b"
    r"|\bwhich\s"
    r"|\btype\s+-[tP]\b"
    r")"
)
# Redirection into a file (or tee) can act on the host, even when a --help flag
# is present: `echo --help > /tmp/f` writes a file.
HOST_WRITE_REDIRECT = re.compile(r"\s>{1,2}\s*\S|\btee\s")


def is_read_only_probe(action: str) -> bool:
    """True only for a probe that cannot act: matches the probe shape and writes nothing."""
    if HOST_WRITE_REDIRECT.search(action):
        return False
    return bool(READ_ONLY_PROBE.search(action))


# For tool calls, require corroboration: a high off-topic score by itself has
# produced false positives on legitimate git commits. The independent necessity
# question must also say the action is unnecessary.
OFF_TOPIC_THRESHOLD = 0.80
UNNECESSARY_THRESHOLD = 0.75
CLEARLY_UNNECESSARY_THRESHOLD = 0.88
EXECUTE_MAX_FOR_VETO = 0.35
STOP_OFF_TOPIC_THRESHOLD = 0.88
STOP_UNNECESSARY_THRESHOLD = 0.80


@dataclass(frozen=True, slots=True)
class PolicyVerdict:
    """Intervention decision; empty reason means allow."""

    deny: bool
    reason: str = ""


def valid_scores(values: Mapping[str, object], expected: Sequence[str]) -> bool:
    """Reject malformed or missing answers instead of treating them as zeros."""
    return all(
        name in values
        and isinstance(values[name], (int, float))
        and not isinstance(values[name], bool)
        and math.isfinite(float(values[name]))
        and 0 <= float(values[name]) <= 1
        for name in expected
    )


def prohibited_full_ci(action: str, prompts: Sequence[str]) -> bool:
    """Honor the latest explicit instruction about `mise run ci`.

    `prompts` must contain *human/delegated task messages only*, in oldest-first
    order, not tool output. An explicit later authorization overrides an earlier
    prohibition; an unrelated later prompt does not.
    """
    if not FULL_CI_CALL.search(action):
        return False
    for prompt in reversed(prompts):
        negative = FULL_CI_NEGATIVE.search(prompt)
        positive = FULL_CI_POSITIVE.search(prompt)
        if negative and (not positive or negative.start() <= positive.start()):
            return True
        if positive:
            return False
    return False


def evaluate_tool(scores: Mapping[str, float]) -> PolicyVerdict:
    """Veto a proposed call only with corroborating, strong model signals."""
    required = ("OffTopic", "UnnecessaryWork", "execute_proposed_call")
    if not valid_scores(scores, required):
        return PolicyVerdict(False, "judge-incomplete-allow")

    off_topic = scores["OffTopic"]
    unnecessary = scores["UnnecessaryWork"]
    execute = scores["execute_proposed_call"]
    # Model support wins outright. If the judge believes executing is the right
    # move, no other detector overrides it — that is what keeps legitimate broad
    # git work from being blocked by a spurious off-topic score.
    if execute > EXECUTE_MAX_FOR_VETO:
        return PolicyVerdict(False, "execution-supported-allow")
    # Otherwise the two waste questions must corroborate. A single signal is not
    # enough: an earlier single-signal variant denied three legitimate edits to
    # this very guard's source. A well-framed state already clears both bars —
    # `pkill` against "Push the current branch" scores 0.94 / 0.96 / 0.03 — so
    # the corroboration costs nothing where the task is right, and it is what
    # keeps mid-band noise from blocking real work where the task is poor.
    if off_topic >= OFF_TOPIC_THRESHOLD and unnecessary >= UNNECESSARY_THRESHOLD:
        return PolicyVerdict(True, "off-task-and-unnecessary")
    if unnecessary >= CLEARLY_UNNECESSARY_THRESHOLD:
        return PolicyVerdict(True, "clearly-unnecessary")
    return PolicyVerdict(False, "insufficient-evidence-allow")


def evaluate_stop(scores: Mapping[str, float]) -> PolicyVerdict:
    """Block an off-task ending only on stronger evidence than a tool call.

    The candidate must be the *final assistant message*, not a summary of past
    calls; historical detours alone cannot justify blocking a completed answer.
    """
    required = ("OffTopic", "UnnecessaryWork")
    if not valid_scores(scores, required):
        return PolicyVerdict(False, "judge-incomplete-allow")
    if (
        scores["OffTopic"] >= STOP_OFF_TOPIC_THRESHOLD
        and scores["UnnecessaryWork"] >= STOP_UNNECESSARY_THRESHOLD
    ):
        return PolicyVerdict(True, "off-task-ending")
    return PolicyVerdict(False, "on-task-or-uncertain-allow")
