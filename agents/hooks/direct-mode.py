#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""~/.agents/hooks/direct-mode.py on|off — toggles orchestrator-only's
per-session escape hatch (see ~/.agents/available-skills/direct/SKILL.md and
~/.agents/available-skills/orchestrate/SKILL.md, which call this).

Session id, in order: GROK_SESSION_ID, CLAUDE_CODE_SESSION_ID, then the most
recently modified per-session state file under $STATE_DIR
(bash-history-<session>.tsv, written by bash-signature-record.py's
PostToolUse hook on every completed Bash call; falls back to
edit-count-<session>.txt or agent-spawn-<session>.txt). The mtime guess is
INFERENCE and marks the wrong session when another harness is busy — env
vars are the live session. The script echoes the session id it acted on so
the caller can sanity-check it.

A CLI utility, not a hook: no stdin JSON, no run_hook fail-open contract —
it exits 1 with a usage message on bad args, like the .sh it replaces.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))

from hook_common import HookSettings, file_mtime

# Grok first so a Grok process binds GROK_SESSION_ID even when
# CLAUDE_CODE_SESSION_ID is also set. The mtime guess is last.
SESSION_ID_ENVS = ("GROK_SESSION_ID", "CLAUDE_CODE_SESSION_ID")
USAGE = "usage: {prog} on|off"
NO_SESSION_STATE_MESSAGE = (
    "direct-mode: no session state found yet — run any Bash/Edit command first, then retry."
)
# Filename -> (prefix, suffix) for each per-session state family latest_session_id scans,
# in the same precedence-by-recency order as direct-mode.sh's glob.
SESSION_STATE_GLOBS = (
    ("bash-history-", ".tsv"),
    ("edit-count-", ".txt"),
    ("agent-spawn-", ".txt"),
)


def _session_id_from_filename(name: str, prefix: str, suffix: str) -> str:
    return name[len(prefix) : -len(suffix)]


def live_session_id() -> str | None:
    """The harness-exported id for this process, or None when neither is set."""
    for key in SESSION_ID_ENVS:
        value = os.environ.get(key, "").strip()
        if value:
            return value
    return None


def latest_session_id(state_dir: Path) -> str | None:
    """The session id embedded in the most recently modified per-session state file."""
    newest_path: Path | None = None
    newest_mtime = 0
    for prefix, suffix in SESSION_STATE_GLOBS:
        for candidate in state_dir.glob(f"{prefix}*{suffix}"):
            mtime = file_mtime(candidate)
            if mtime is not None and mtime > newest_mtime:
                newest_mtime = mtime
                newest_path = candidate
    if newest_path is None:
        return None
    for prefix, suffix in SESSION_STATE_GLOBS:
        if newest_path.name.startswith(prefix) and newest_path.name.endswith(suffix):
            return _session_id_from_filename(newest_path.name, prefix, suffix)
    return None


def main(argv: list[str]) -> int:
    # Argument-count check only, matching direct-mode.sh's `[ $# -eq 1 ]` —
    # an unrecognized single argument (neither on nor off) still runs the
    # session lookup below and is rejected by the trailing case statement,
    # not here. Replicated for parity, not because it's the ideal order.
    if len(argv) != 2:
        print(USAGE.format(prog=argv[0] if argv else "direct-mode.py"), file=sys.stderr)
        return 1

    settings = HookSettings.from_env()
    settings.state_dir.mkdir(parents=True, exist_ok=True)

    session_id = live_session_id() or latest_session_id(settings.state_dir)
    if session_id is None:
        print(NO_SESSION_STATE_MESSAGE, file=sys.stderr)
        return 1

    marker = settings.state_dir / f"direct-mode-{session_id}"
    match argv[1]:
        case "on":
            marker.touch()
            print(f"direct mode ON for session {session_id}")
        case "off":
            marker.unlink(missing_ok=True)
            print(f"direct mode OFF for session {session_id}")
        case _:
            print(USAGE.format(prog=argv[0]), file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
