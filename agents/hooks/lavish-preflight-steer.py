#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""PreToolUse (tool.before) — raw lavish-axi opens must go through lavish-preflight.

MI-001 (at-51q2ph, 2026-10-24): the lavish editor's layout detector reported
overlapping-text errors only to the human's warning badge; two agents handed
over broken artifacts on the same day. `lavish-preflight <html-file>` is now
the required entry point (named in the lavish skill and ~/.agents/AGENTS.md):
it checks the artifact statically, opens the session, runs the editor's
detector in headless Chrome, and fails with rule + selector on unresolved
errors. A raw `npx -y lavish-axi <file>.html` skips all of that, so this hook
denies it and steers to the gate.

Scope, deliberately conservative — a false block costs more than a miss: deny
only commands that mention lavish-axi and an .html file, do not already
mention `preflight` (the gate's own invocation), and do not contain a
non-open subcommand (poll/reply/end/export/share/design/playbook/stop). The
lavish skill text remains the enforcement layer this hook cannot replace.

Known limitation (respected, logged on the at-51q2ph objective): in omp,
run_command is invoked as `write xd://…` and the bridge passes the raw tool
name, so tool-name matchers may never fire there — the lavish skill text is
omp's enforcement. This hook covers the harnesses whose tool.before payloads
do reach agent-hooks (Claude Code, Codex, Grok, Copilot, ...).

Fails open inside run_hook (a crash logs and exits 0); the config's
on_failure = "block" turns a nonzero exit into a block at the harness.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))

from hook_common import Decision, HookEvent, run_hook

HOOK_NAME = "lavish-preflight-steer"

SUBCOMMAND_RE = re.compile(
    r"lavish-axi\s+(?:-y\s+)?(poll|reply|end|export|share|design|playbook|stop)\b"
)
HTML_RE = re.compile(r"\S+\.html\b")

DENY_REASON = (
    "This raw lavish-axi open bypasses the preflight gate. Run "
    "`lavish-preflight <html-file>` instead: it checks the artifact directory, "
    "opens the session, runs the editor's layout detector in headless Chrome, "
    "and exits 1 with the rule + selector of any unresolved layout error so you "
    "fix the page before the human sees it. Rerun until it prints OK, then hand "
    "over the URL it prints. (If the gate cannot reopen a session the user ended "
    "from the browser, that is a user decision — ask.) poll/reply/end/export/share "
    "are not opens; run those with npx -y lavish-axi as usual."
)


def decide(event: HookEvent) -> Decision | None:
    if event.tool_name != "Bash":
        return None
    command = event.tool_input("command")
    if not command:
        return None
    if "preflight" in command:
        return None
    if "lavish-axi" not in command:
        return None
    if SUBCOMMAND_RE.search(command):
        return None
    if not HTML_RE.search(command):
        return None
    return Decision.deny(DENY_REASON, log_detail="lavish-preflight-steer")


if __name__ == "__main__":
    run_hook(HOOK_NAME, decide)
