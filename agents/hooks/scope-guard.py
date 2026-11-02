#!/Users/zbornheimer/.local/share/mise/installs/python/3.13/bin/python3
# uv's `--script` resolution costs seconds per tool call; this mise python
# already carries pyyaml, so the hook boots in tens of milliseconds. The
# PEP 723 header below still serves `uv run --script` when run that way.
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml>=6.0"]
# ///
"""PreToolUse + Stop — put a drifting agent back on the user's current task.

Two interception points over one policy (``lib/scope_decide.py``):

  tool.before (``PreToolUse``) -> deny the off-task proposed call; the reason is the
      correction, so the agent reads it while it can still act on it (``Decision.deny``).
  turn.stop (``Stop``)         -> block the turn that ended off-task with the same
      correction, so it resumes and finishes (``Decision.block``).

The in-turn refusal is the primary mechanism: measured over the frozen intervention
scenarios, redirecting at the proposed call finished the task with nothing unrelated run in
5/12 trials, while correcting after the fact (steer) ran the detour in 12/12 and refusing
without a usable next step (stop) finished the task in 0/12
(mastra/src/evals/scope-drift/experiment.ts).

Fails OPEN on everything it cannot judge — no user task, no key, an outage, a timeout,
garbage, a middle score, a reached cap, ``SCOPE_GUARD=off`` — and logs why. The policy and
its measured constants live in lib/scope_decide.py.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))

from hook_common import Decision, HookEvent, run_hook
from scope_decide import HOOK_NAME, scope_decision


def decide(event: HookEvent) -> Decision | None:
    """One catalog row per event; the event in the payload decides which one this is."""
    return scope_decision(event)


if __name__ == "__main__":
    run_hook(HOOK_NAME, decide)
