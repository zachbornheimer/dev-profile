"""Stand-in for ``typesafe.py interrogate`` in scope-guard tests (``HC_SCOPE_JUDGE_CLI``).

``SCOPE_JUDGE_FAKE`` picks the behavior:

  score:<0-1>  the detector's score for the candidate, e.g. ``score:0.81``
  no-key       interrogate's own failure path: the reason on stderr, exit 1
  crash        exits 1 with a traceback
  hang         sleeps past any hook timeout
  garbage      prints something that is not JSON
  no-source    a reply with no ``source``: the unavailable shape
  no-noul      a reply whose answer carries no ``noul``

A score rather than a named band, because the guard's two bars (a tool call is denied only
in the high-confidence band, a turn end is corrected from the lower one) are the thing under
test, and the live traffic that set them has to be replayed at its own numbers.

The hook reads ``answers.question_1.noul``, which is what ``interrogate`` returns for the
single question it forwards. Every call is appended to ``SCOPE_JUDGE_CALLS`` when that names
a file, so a test can prove the guard never reached the judge.
"""

from __future__ import annotations

import json
import os
import sys
import time

FAKE_ENV = "SCOPE_JUDGE_FAKE"
CALLS_ENV = "SCOPE_JUDGE_CALLS"
HANG_SECS = 60
QUESTION_ID = "question_1"
SCORE_PREFIX = "score:"


def reply(score: float) -> dict[str, object]:
    return {
        "answers": {QUESTION_ID: {"type": "noul", "noul": score}},
        "usage": {"input_tokens": 700, "output_tokens": 22, "cost": 0},
        "source": "typesafe",
    }


def record(request: str) -> None:
    path = os.environ.get(CALLS_ENV, "")
    if not path:
        return
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(request.rstrip("\n") + "\n")


def main() -> int:
    request = sys.stdin.read()
    record(request)
    mode = os.environ.get(FAKE_ENV, "score:0.97")
    if mode.startswith(SCORE_PREFIX):
        json.dump(reply(float(mode[len(SCORE_PREFIX) :])), sys.stdout)
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
        print(json.dumps({"answers": {QUESTION_ID: {"type": "noul"}}, "source": "typesafe"}))
        return 0
    raise SystemExit(f"unknown {FAKE_ENV}: {mode}")


if __name__ == "__main__":
    sys.exit(main())
