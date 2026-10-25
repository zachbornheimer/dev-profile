#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""UserPromptSubmit: learn from this session when the user sounds frustrated.

Two ways to decide. As its own hook it scores the prompt with
``lib/frustration.py`` (lexical signals, repeated requests, a run of tool
errors). Run as ``frustration-learn.py --judged <p>`` it takes the verdict of
the ``detect_frustration`` capability, which ``prompt-submit-capabilities.sh``
asks of every prompt, and skips the scoring. Either way it starts
``~/.agents/bin/learn-launch`` detached, which runs the ``learn-from-transcript``
workflow on the session, and lets the prompt through untouched.
One launch per session: a marker file in the state dir enforces it, across both
ways. The manual ``/learn`` command in omp is the way to ask for another.

A session with ``LEARNER=1`` never launches a learning run.

Never blocks, never adds context, never fails the prompt: the launcher runs
detached and its errors go to ``frustration-learn.err`` in the hook state dir.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))

from frustration import score, transcript_signals
from hook_common import Decision, HookEvent, run_hook
from hook_common.settings import HookSettings

HOOK_NAME = "frustration-learn"
LAUNCHER = Path.home() / ".agents" / "bin" / "learn-launch"
OMP_SESSION_NAME = re.compile(r"_([0-9a-f]{8}-[0-9a-f-]{27})\.jsonl$")
SAFE = re.compile(r"[^A-Za-z0-9._-]")


def session_identity(event: HookEvent, env: dict[str, str]) -> tuple[str, Path | None]:
    """(``<harness>:<id>``, transcript path); ref is ``""`` when the session cannot be named.

    The payload's ``transcript_path`` is the only trusted source. omp's bridge adds it and
    reports the agent as ``claude``, so an omp transcript file name decides the harness. The
    process env is not used: a nested omp inherits its parent's PI_SESSION_FILE.
    """
    transcript = event.field("transcript_path", "transcriptPath")
    path = Path(transcript).expanduser() if transcript else None
    found = OMP_SESSION_NAME.search(transcript)
    if found:
        return f"omp:{found.group(1)}", path
    harness, session_id = env.get("AGENT_HOOKS_AGENT", ""), event.session_id
    return (f"{harness}:{session_id}" if harness and session_id else ""), path


def claim_launch(ref: str) -> bool:
    """True exactly once per session ref, even when two prompts race."""
    directory = HookSettings.from_env().state_dir / HOOK_NAME
    directory.mkdir(parents=True, exist_ok=True)
    try:
        with (directory / SAFE.sub("_", ref)).open("x"):
            return True
    except FileExistsError:
        return False


def launch(ref: str, reasons: str, env: dict[str, str]) -> None:
    command = env.get("LEARN_LAUNCH_CMD") or str(LAUNCHER)
    argv = [command, ref, "--reason", f"frustration signals: {reasons}"]
    state = HookSettings.from_env().state_dir
    state.mkdir(parents=True, exist_ok=True)
    with (state / f"{HOOK_NAME}.err").open("ab") as errors:
        subprocess.Popen(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=errors,
            start_new_session=True,
        )


def judged_probability(argv: list[str]) -> float | None:
    """P(frustrated) from ``--judged <p>``, or None when the hook runs as itself."""
    if len(argv) == 3 and argv[1] == "--judged":
        return float(argv[2])
    return None


def decide(event: HookEvent, judged: float | None = None) -> Decision | None:
    env = dict(os.environ)
    if env.get("LEARNER") == "1":
        return None
    prompt = event.field("prompt", "prompt")
    if not prompt.strip():
        return None

    ref, transcript = session_identity(event, env)
    if judged is not None:
        reasons = f"judged(p={judged:.2f})"
    else:
        prior, errors = transcript_signals(transcript, prompt)
        result = score(prompt, prior, errors)
        if not result.triggered:
            return None
        reasons = f"{','.join(result.reasons)} score={result.total}"
    if not ref:
        return Decision.no_objection("unnamed-session", log_label="skip")
    if not claim_launch(ref):
        return Decision.no_objection(f"{ref} already launched", log_label="skip")

    launch(ref, reasons, env)
    return Decision.no_objection(f"{ref} {reasons}", log_label="launch")


if __name__ == "__main__":
    judged = judged_probability(sys.argv)
    run_hook(HOOK_NAME, lambda event: decide(event, judged))
