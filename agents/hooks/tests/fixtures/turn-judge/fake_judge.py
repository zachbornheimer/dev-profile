"""Stand-in for ``typesafe.py judge-turn`` in hook tests (HC_TURN_JUDGE_CLI points here).

TURN_JUDGE_FAKE picks the behavior:
  unavailable  TypeSafe answered with a fallback (no key)
  unavailable-multihop  fallback after every base URL failed (carries `detail`)
  crash        exits 1 with a traceback
  hang         sleeps past any hook timeout
  garbage      prints something that is not JSON
  <path>       a JSON file of TypeSafe answers: runs the REAL judge-turn CLI
               with an HTTP stub that returns them, so the real policy decides
"""

from __future__ import annotations

import importlib
import io
import json
import os
import sys
import time
from pathlib import Path
from typing import Self

FAKE_ENV = "TURN_JUDGE_FAKE"
HANG_SECS = 60
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))
from typesafe_location import TYPESAFE_SCRIPTS_DIR as TYPESAFE_SCRIPTS

FAKE_KEY = "fake-judge-key"
_FALLBACK = {"action": "allow", "block_kind": "none", "source": "fallback"}
FALLBACK_VERDICTS = {
    "unavailable": {**_FALLBACK, "reason": "missing key"},
    "unavailable-multihop": {
        **_FALLBACK,
        "reason": "http 400",
        "detail": "api.typesafe.ai http 429 > localhost http 400",
    },
}


class _Response(io.BytesIO):
    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args: object) -> None:
        return None


def _real_cli_with_answers(answers_path: str) -> int:
    sys.path.insert(0, str(TYPESAFE_SCRIPTS))
    typesafe = importlib.import_module("typesafe")
    body = json.dumps({"answers": json.loads(Path(answers_path).read_text()), "usage": {}}).encode()

    def getenv(name: str, default: str | None = None) -> str | None:
        return FAKE_KEY if name == typesafe.API_KEY_ENV else os.environ.get(name, default)

    return typesafe.main(
        ["judge-turn", "--json"], getenv=getenv, urlopen=lambda *_a, **_k: _Response(body)
    )


def main() -> int:
    mode = os.environ.get(FAKE_ENV, "unavailable")
    if mode in FALLBACK_VERDICTS:
        print(json.dumps(FALLBACK_VERDICTS[mode]))
        return 0
    if mode == "crash":
        raise RuntimeError("fake judge crashed")
    if mode == "hang":
        time.sleep(HANG_SECS)
        return 0
    if mode == "garbage":
        print("not json")
        return 0
    return _real_cli_with_answers(mode)


if __name__ == "__main__":
    sys.exit(main())
