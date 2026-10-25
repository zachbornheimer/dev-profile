#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""PreToolUse (Bash matcher) — process-kill guard.

Incident: `pkill -f "wt step commit"` killed worktrunk mid-commit and
corrupted an in-flight signed commit and its hooks.

Denies killing `wt` by pattern (pkill, killall, pgrep|xargs kill,
kill $(pgrep ...)) and steers any unscoped `pkill -f` to the age-limited
`pkill-aged` wrapper. Rules live in lib/process_kill_rules.py.

Unlike orchestrator-only, this applies to every caller, subagents and
workers included: they are the ones running these commands. Claude Code,
Codex and Hermes register it; Grok reaches it through its Claude-compat
scan of ~/.claude/settings.json; OpenCode through its claude-hooks plugin.

Fails OPEN on any parse error or unexpected input: a false block is far
more costly than a missed check.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))

from command_words import simple_commands
from hook_common import Decision, HookEvent, run_hook
from process_kill_rules import deny_reason

HOOK_NAME = "process-kill-guard"


def decide(event: HookEvent) -> Decision | None:
    if event.tool_name != "Bash":
        return None
    command = event.tool_input("command")
    if not command:
        return None
    reason = deny_reason(simple_commands(command), command)
    if reason:
        return Decision.deny(f"{HOOK_NAME}: {reason}")
    return Decision.no_objection(f"{HOOK_NAME}:no-process-kill-risk")


if __name__ == "__main__":
    run_hook(HOOK_NAME, decide)
