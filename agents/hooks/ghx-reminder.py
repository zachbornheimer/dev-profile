#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""PreToolUse (Bash) — soft reminder to route rate-limit-heavy gh calls
through ghx (~/Developer/Personal/ghx). Informational only: never denies,
never rewrites the command. Fails OPEN (via run_hook) so it can never
become a Bash-tool blocker.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))

from hook_common import Decision, HookEvent, run_hook

HOOK_NAME = "ghx-reminder"
GHX_MARKER = "ghx"
RATE_LIMITED_GH_CALL = re.compile(
    r"(^|[;&|\s])gh\s+"
    r"(search|api\s+(/)?graphql|pr\s+(list|view|status)|issue\s+(list|view|status))"
)
REMINDER_TEXT = (
    "Reminder: prefer ghx over raw gh for search/GraphQL-backed calls (gh search, gh api "
    "graphql, gh pr|issue list/view). ghx takes identical args, checks the correct "
    "rate-limit pool first, and never stalls — just replace gh with ghx. ghx doctor shows "
    "pool headroom."
)


def decide(event: HookEvent) -> Decision | None:
    if event.tool_name != "Bash":
        return None
    command = event.tool_input("command")
    if not command:
        return None
    if GHX_MARKER in command:
        return None
    if not RATE_LIMITED_GH_CALL.search(command):
        return None
    return Decision.context(REMINDER_TEXT, event_name="PreToolUse")


if __name__ == "__main__":
    run_hook(HOOK_NAME, decide)
