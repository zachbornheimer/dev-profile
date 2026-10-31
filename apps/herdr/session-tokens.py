#!/usr/bin/env python3
"""Report each herdr agent's session id as pane metadata so the sidebar can
render it as a `$session` token.

Herdr keeps an agent's session id (the value claude resumes with, the path pi
writes) but exposes it only through the socket API, not as a sidebar token.
Custom pane metadata is the supported bridge, and it expires, so this writer
re-reports every agent on each run and sets a TTL longer than the run interval.

Each herdr session runs its own server with its own panes, so this writer visits
every running session and passes `--session` to each call. Without it, only the
default server's panes get metadata and the other sessions show no `$session`.

Display is a config decision, not this script's: a pane that reports `session`
still shows nothing until a row lists `$session`.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HERDR = "/opt/homebrew/bin/herdr"
SOURCE = "herdr-session-tokens"
TTL_MS = 180_000  # three run intervals of headroom
SHORT_ID_LENGTH = 8


def running_sessions() -> list[str]:
    """Names of herdr sessions whose server is live, default included."""
    done = subprocess.run(
        [HERDR, "session", "list", "--json"],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    if done.returncode != 0:
        raise RuntimeError(done.stderr.strip() or "herdr session list failed")
    sessions = json.loads(done.stdout)["sessions"]
    return [session["name"] for session in sessions if session["running"]]


def snapshot(session: str) -> dict:
    """Live server state for one session."""
    done = subprocess.run(
        [HERDR, "--session", session, "api", "snapshot"],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    if done.returncode != 0:
        raise RuntimeError(done.stderr.strip() or "herdr api snapshot failed")
    return json.loads(done.stdout)["result"]["snapshot"]


def short_session(agent_session: dict) -> str | None:
    """First block of the session id: what a human types to resume.

    `kind = "id"` is a bare UUID; `kind = "path"` is a session file whose
    basename ends in the UUID after the last `_`. Both reduce to 8 characters,
    which is the difference between fitting in a 32-column sidebar and not.
    """
    raw = (agent_session or {}).get("value") or ""
    if not raw:
        return None
    if agent_session.get("kind") == "path":
        raw = Path(raw).name.removesuffix(".jsonl").rsplit("_", 1)[-1]
    return raw.split("-", 1)[0][:SHORT_ID_LENGTH] or None


def main() -> int:
    try:
        sessions = running_sessions()
    except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired) as error:
        # Herdr not running is the normal case between sessions; stay silent so
        # launchd does not log a failure every minute.
        print(f"session-tokens: skipped ({error})", file=sys.stderr)
        return 0

    for session in sessions:
        try:
            agents = snapshot(session).get("agents", [])
        except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired) as error:
            print(f"session-tokens: {session} skipped ({error})", file=sys.stderr)
            continue

        reported = 0
        for agent in agents:
            short = short_session(agent.get("agent_session"))
            if not short:
                continue
            done = subprocess.run(
                [
                    HERDR,
                    "--session",
                    session,
                    "pane",
                    "report-metadata",
                    agent["pane_id"],
                    "--source",
                    SOURCE,
                    "--token",
                    f"session={short}",
                    "--ttl-ms",
                    str(TTL_MS),
                ],
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )
            if done.returncode == 0:
                reported += 1
            else:
                print(
                    f"session-tokens: {session} {agent['pane_id']} failed: {done.stderr.strip()}",
                    file=sys.stderr,
                )

        print(f"session-tokens: {session} reported {reported}/{len(agents)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
