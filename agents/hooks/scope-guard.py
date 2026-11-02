#!/usr/bin/env python3
# A PATH-resolved python3 is the fastest portable start (~0.35–0.96 s when the
# resolved interpreter is 3.10+ with yaml, vs ~1.5 s for uv or mise exec), but
# a fleet box can hand the hook an older, barer interpreter (lib/scope_decide.py
# needs 3.10+ and yaml), so the bootstrap below re-execs through uv — whose
# script env carries the PEP 723 requirements — and fails open when no capable
# start exists. The PEP 723 header serves that fallback.
#
# Measured starts (env -i, 5-run medians): capable interpreter 0.35–0.96 s;
# under omp's real PATH (mise shim -> /usr/bin/python3 3.9 -> uv re-exec)
# ~2.4 s — the 1.6 s mise-shim hop is the dominant cost, tracked separately.
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

import importlib.util
import os
import sys

REEXEC_ENV = "HC_SCOPE_GUARD_REEXEC"
# lib needs dataclass ``slots`` (3.10+); the PEP 723 header above states the same floor.
LIB_MINIMUM_PYTHON = (3, 10)


def _needs_script_env() -> bool:
    """``lib`` needs ``LIB_MINIMUM_PYTHON`` and yaml; a bare PATH python3 may offer neither."""
    if tuple(sys.version_info[:2]) < LIB_MINIMUM_PYTHON:
        return True
    try:
        return importlib.util.find_spec("yaml") is None
    except (ImportError, ValueError):
        return True


if _needs_script_env() and not os.environ.get(REEXEC_ENV):
    # uv replaces this process, so its interpreter is the hook's; the marker
    # stops a pathological uv from looping, and a missing uv fails open.
    os.environ[REEXEC_ENV] = "1"
    try:
        os.execvp("uv", ["uv", "run", "--script", os.path.abspath(__file__)])
    except OSError as exc:
        sys.stderr.write(f"scope-guard: no capable interpreter start: {exc}\n")
        sys.exit(0)

from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))

from hook_common import Decision, HookEvent, run_hook
from scope_decide import HOOK_NAME, scope_decision


def decide(event: HookEvent) -> Decision | None:
    """One catalog row per event; the event in the payload decides which one this is."""
    return scope_decision(event)


if __name__ == "__main__":
    run_hook(HOOK_NAME, decide)
