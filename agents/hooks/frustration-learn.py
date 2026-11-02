#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Prompt route: learn from this session when a model judged the user frustrated.

Run as ``frustration-learn.py --judged <p>``. ``p`` is P(frustrated) from the
``Frustrated`` question of the prompt-submit batch; the route that starts this
script (omp's prompt-hooks extension, or prompt-respond.py elsewhere) already
applied the bar. The verdict is always a model's: this script never scores the
prompt's words, and without ``--judged`` it launches nothing.

It starts ``~/.agents/bin/learn-launch`` detached, which runs the
``learn-from-transcript`` workflow on the session, and lets the prompt through
untouched. At most one launch per session every four hours: a stamp file per
session in the state dir enforces it. Set ``FRUSTRATION_LEARN_COOLDOWN_SECONDS``
to change the window. The manual ``/learn`` command in omp runs one at any time.

A session with ``LEARNER=1`` never launches a learning run.

Never blocks, never adds context, never fails the prompt: the launcher runs
detached and its errors go to ``frustration-learn.err`` in the hook state dir.
"""

from __future__ import annotations

import fcntl
import os
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))

from hook_common import Decision, HookEvent, run_hook
from hook_common.settings import HookSettings

HOOK_NAME = "frustration-learn"
LAUNCHER = Path.home() / ".agents" / "bin" / "learn-launch"
OMP_SESSION_NAME = re.compile(r"_([0-9a-f]{8}-[0-9a-f-]{27})\.jsonl$")
SAFE = re.compile(r"[^A-Za-z0-9._-]")
COOLDOWN_SECONDS = 4 * 60 * 60


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
        if path is None or not path.is_file():
            return "", path
        return f"omp:{found.group(1)}", path
    if env.get("AGENT_HOOKS_HOST") == "omp":
        return "", path
    if path is not None and not path.is_file():
        return "", path
    harness, session_id = env.get("AGENT_HOOKS_AGENT", ""), event.session_id
    return (f"{harness}:{session_id}" if harness and session_id else ""), path


def cooldown_seconds(env: dict[str, str]) -> float:
    return float(env.get("FRUSTRATION_LEARN_COOLDOWN_SECONDS") or COOLDOWN_SECONDS)


def claim_launch(ref: str, cooldown: float) -> Path | None:
    """Stamp path when this session has not launched within ``cooldown`` seconds, else None.

    The stamp file holds one line per launch; its mtime is the last one. An
    exclusive lock makes the check-and-stamp atomic, so two racing prompts
    still launch once.
    """
    directory = HookSettings.from_env().state_dir / HOOK_NAME
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / SAFE.sub("_", ref)
    with target.open("a") as stamp:
        fcntl.flock(stamp, fcntl.LOCK_EX)
        last = os.fstat(stamp.fileno())
        now = time.time()
        if last.st_size and now - last.st_mtime < cooldown:
            return None
        stamp.write(f"{now:.0f}\n")
        return target


def launch(
    ref: str, reasons: str, env: dict[str, str], stamp: Path | None = None
) -> None:
    # LEARN_LAUNCH_CMD is the test seam; production runs ~/.agents/bin/learn-launch.
    launcher = env.get("LEARN_LAUNCH_CMD") or str(LAUNCHER)
    child_env = {**env, "LEARNER": "1", "AGENTMUX_NESTED_RUN": "1"}
    if stamp is not None:
        child_env["LEARN_STAMP_FILE"] = str(stamp)
    state = HookSettings.from_env().state_dir
    state.mkdir(parents=True, exist_ok=True)
    with (state / f"{HOOK_NAME}.err").open("ab") as errors:
        # Argument list, no shell: /usr/bin/env executes the launcher with these exact arguments.
        subprocess.Popen(
            [
                "/usr/bin/env",
                launcher,
                ref,
                "--reason",
                f"frustration signals: {reasons}",
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=errors,
            env=child_env,
            start_new_session=True,
        )


def judged_probability(argv: list[str]) -> float | None:
    """P(frustrated) from ``--judged <p>``, or None when no model verdict was passed."""
    if len(argv) == 3 and argv[1] == "--judged":
        return float(argv[2])
    return None


def decide(event: HookEvent, judged: float | None) -> Decision | None:
    env = dict(os.environ)
    if env.get("LEARNER") == "1":
        return None
    if judged is None:
        return Decision.no_objection("no judged verdict", log_label="skip")
    if not event.field("prompt", "prompt").strip():
        return None

    ref, _ = session_identity(event, env)
    if not ref:
        return Decision.no_objection("unnamed-session", log_label="skip")
    stamp = claim_launch(ref, cooldown_seconds(env))
    if stamp is None:
        return Decision.no_objection(
            f"{ref} launched within the cooldown", log_label="skip"
        )

    reasons = f"judged(p={judged:.2f})"
    launch(ref, reasons, env, stamp)
    return Decision.no_objection(f"{ref} {reasons}", log_label="launch")


if __name__ == "__main__":
    judged = judged_probability(sys.argv)
    run_hook(HOOK_NAME, lambda event: decide(event, judged))
