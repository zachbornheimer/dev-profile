"""Replay the three measured completion-gate misfires through the judge policy.

Fixtures are the exact judged answers, evidence digests, and empty user_request
logged in completion-gate-judgments.jsonl at lines 18115 and 18120 (the omp
"advise me on the syntax for PR #9" answers the gate blocked into two
unrequested review runs) and line 18176 (the subagent turn whose finished
report the gate ate, leaving the parent an empty tool result).

Contract under test: with no user_request there is no ask to leave work
against — the parent owns the ask and the audit. decide_turn must allow every
such turn while still computing and returning the signals, and the verdict
must be a real judged one (source typesafe), not a fallback allow.

Run:  python3 completion_gate_replay.py             # exit 0 when all three allow
      python3 completion_gate_replay.py <fixtures.jsonl>

Extract the fixtures with:
  sed -n '18115p;18120p;18176p' \
    ~/.agents/hooks/state/completion-gate-judgments.jsonl > /tmp/gate-fixtures.jsonl
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

TYPESAFE_SCRIPTS = (
    Path.home() / ".agents" / "available-skills" / "typesafe-ai" / "scripts"
)
if str(TYPESAFE_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(TYPESAFE_SCRIPTS))

turn_judge = importlib.import_module("turn_judge")

DEFAULT_FIXTURES = Path("/tmp/gate-fixtures.jsonl")
EXTRACT_HINT = (
    "sed -n '18115p;18120p;18176p' "
    "~/.agents/hooks/state/completion-gate-judgments.jsonl > /tmp/gate-fixtures.jsonl"
)


def load_fixtures(path: Path = DEFAULT_FIXTURES) -> list[dict]:
    entries = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not entries:
        raise ValueError(f"no fixtures in {path}")
    return entries


def replay(entry: dict) -> turn_judge.TurnVerdict:
    """Judge one logged turn: its logged answers, evidence digest, and ask."""
    request = entry.get("request") or {}
    return turn_judge.decide_turn(
        entry["answers"],
        request.get("evidence") or {},
        None,
        user_request=str(request.get("user_prompt") or ""),
    )


def check(entry: dict) -> tuple[bool, str]:
    verdict = replay(entry)
    allowed = (
        verdict.action == turn_judge.ACTION_ALLOW
        and verdict.block_kind == turn_judge.BLOCK_NONE
        and verdict.source == turn_judge.SOURCE_TYPESAFE
    )
    detail = (
        f"ts={entry.get('ts')} action={verdict.action} kind={verdict.block_kind} "
        f"source={verdict.source} signals={sorted(verdict.signals)}"
    )
    return allowed, detail


def main(argv: list[str]) -> int:
    path = Path(argv[1]) if len(argv) > 1 else DEFAULT_FIXTURES
    if not path.is_file():
        print(f"fixtures missing: {path}\nextract them with: {EXTRACT_HINT}")
        return 2
    entries = load_fixtures(path)
    failures = 0
    for number, entry in enumerate(entries, 1):
        allowed, detail = check(entry)
        print(
            f"fixture {number}: {'ALLOW (pass)' if allowed else 'BLOCKED (fail)'} | {detail}"
        )
        failures += 0 if allowed else 1
    print(f"{len(entries) - failures}/{len(entries)} misfires now allow")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
