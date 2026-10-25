#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.9"
# dependencies = []
# ///
# SessionStart (matcher: compact) — re-assert the communication contract at the
# TAIL of the freshly compacted context.
#
# Why this exists: the contract lives in two places that both sit at position 0
# of the request — the system prompt (output style "Zach Comms") and CLAUDE.md
# (a user message after the system prompt). Both are always present, but neither
# is RECENT. Measured drift (session b5fed331): mean reply length climbed
# monotonically 270 -> 1814 chars over 117 turns as the model's own verbose
# replies accumulated as in-context examples. This hook puts the rule back where
# attention is strongest, once per compaction, at negligible cache cost.
#
# Never blocks. Fails open (exit 0, best-effort output) on any error.
import os
import select
import sys
from datetime import datetime, timezone
from pathlib import Path

STDIN_TIMEOUT_SECS = 5
HOOKS_LOG = Path.home() / ".claude" / "hooks" / "state" / "hooks.log"

MESSAGE = """\
Communication contract — re-asserted after compaction. The transcript above is a
summary; the verbose replies that preceded it are gone, and their length is not a
precedent. Reset to the contract:

- Lead with the answer. First sentence carries the conclusion.
- Most replies are 1-5 sentences. Length does not grow across a conversation.
- No praise, no validating the user's concern before answering it, no restating
  the request. Agreement is implied by the answer.
- Evidence for claims that matter: file:line, SHA, exact command, test output.
  Say "I didn't verify that" rather than guessing.
- Status-report format (Outcome / Findings / Next action / Evidence) is for
  multi-step work only. A single long turn does not qualify.
"""


def drain_stdin() -> None:
    """Drain hook stdin so the caller never blocks on a full pipe.

    The payload itself is unused — this hook emits the same text regardless.
    """
    try:
        while select.select([sys.stdin], [], [], STDIN_TIMEOUT_SECS)[0]:
            if not os.read(sys.stdin.fileno(), 65536):
                break
    except Exception:
        pass


def log(decision: str, detail: str) -> None:
    """Append to the shared hooks.log in hook-common.sh's tab format."""
    try:
        HOOKS_LOG.parent.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        with HOOKS_LOG.open("a") as f:
            f.write(f"{now}\tcomms-recall\t{decision}\t{detail}\n")
    except Exception:
        pass


def main() -> int:
    drain_stdin()
    print(MESSAGE, end="")
    log("emitted", "post-compact-reassert")
    return 0


if __name__ == "__main__":
    sys.exit(main())
