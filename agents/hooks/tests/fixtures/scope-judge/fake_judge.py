"""Stand-in for ``typesafe.py interrogate`` in scope-guard tests (``HC_SCOPE_JUDGE_CLI``).

``SCOPE_JUDGE_FAKE`` picks the behavior:

  scores:<a,b,…>  one score per question the guard asked, in the order it asked them
                 (a tool call: OffTopic, UnnecessaryWork, execute_proposed_call; a Stop:
                 OffTopic, UnnecessaryWork), e.g. ``scores:0.94,0.96,0.03``
  no-key         interrogate's own failure path: the reason on stderr, exit 1
  crash          exits 1 with a traceback
  hang           sleeps past any hook timeout
  garbage        prints something that is not JSON
  no-source      a reply with no ``source``: the unavailable shape
  no-noul        a reply whose answer carries no ``noul``

One score per question, because the tool call denies only on corroborating signals: the
guard asks three questions and each bar (OffTopic 0.80 AND UnnecessaryWork 0.75, or
UnnecessaryWork 0.88 alone, unless execute_proposed_call > 0.35) is independent, so a test
must be able to set every score separately. A count mismatch between the scores given and
the questions asked exits 1 rather than guessing, so a test can never silently pass on
half an answer. The hook reads ``answers.question_<i>.noul``, which is what ``interrogate``
returns for the questions it forwards. Every call is appended to ``SCOPE_JUDGE_CALLS``
when that names a file inside the hook run's state directory (``HC_STATE_DIR_OVERRIDE``),
so a test can prove the guard never reached the judge.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

FAKE_ENV = "SCOPE_JUDGE_FAKE"
CALLS_ENV = "SCOPE_JUDGE_CALLS"
STATE_DIR_ENV = "HC_STATE_DIR_OVERRIDE"
HANG_SECS = 60
SCORES_PREFIX = "scores:"
# Deny-shaped, so a test that forgets its scores fails loudly instead of allowing.
DEFAULT_SCORES = "scores:0.94,0.96,0.03"


def reply(values: list[str]) -> dict[str, object]:
    return {
        "answers": {
            f"question_{index}": {"type": "noul", "noul": float(value)}
            for index, value in enumerate(values, start=1)
        },
        "usage": {"input_tokens": 700, "output_tokens": 22, "cost": 0},
        "source": "typesafe",
    }


def asked_questions(request: str) -> int:
    """How many questions the guard sent, as a plain int; never request text."""
    try:
        questions = json.loads(request).get("questions")
    except ValueError:
        return 0
    return len(questions) if isinstance(questions, list) else 0


def calls_path(raw: str) -> Path | None:
    """``raw`` only when it names a file inside the hook run's state directory."""
    if not raw:
        return None
    state_dir = Path(os.environ.get(STATE_DIR_ENV, "")).resolve()
    candidate = Path(raw)
    if (
        not candidate.is_absolute()
        or ".." in candidate.parts
        or not state_dir.is_dir()
        or not candidate.resolve().is_relative_to(state_dir)
    ):
        return None
    return candidate


def record(request: str) -> None:
    path = calls_path(os.environ.get(CALLS_ENV, ""))
    if path is None:
        return
    with path.open("a", encoding="utf-8") as handle:
        handle.write(request.rstrip("\n") + "\n")


def main() -> int:
    request = sys.stdin.read()
    record(request)
    mode = os.environ.get(FAKE_ENV, DEFAULT_SCORES)
    if mode.startswith(SCORES_PREFIX):
        values = mode[len(SCORES_PREFIX) :].split(",")
        expected = asked_questions(request)
        if len(values) != expected:
            # ``%d`` formats the two counts, never request text, so a hostile
            # request cannot forge this diagnostic line.
            sys.stderr.write(
                "asked %d questions, got %d scores\n" % (expected, len(values))
            )
            return 1
        json.dump(reply(values), sys.stdout)
        sys.stdout.write("\n")
        return 0
    if mode == "no-key":
        print("missing key", file=sys.stderr)
        return 1
    if mode == "crash":
        raise RuntimeError("fake scope judge crashed")
    if mode == "hang":
        time.sleep(HANG_SECS)
        return 0
    if mode == "garbage":
        print("not json")
        return 0
    if mode == "no-source":
        print(json.dumps({"answers": {}, "reason": "missing key"}))
        return 0
    if mode == "no-noul":
        print(json.dumps({"answers": {"question_1": {"type": "noul"}}, "source": "typesafe"}))
        return 0
    raise SystemExit(f"unknown {FAKE_ENV}: {mode}")


if __name__ == "__main__":
    sys.exit(main())
