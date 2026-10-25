#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""PreToolUse (Bash) — the Bash tool is dead surface on this machine.

Every command runs through ``mcp__capability__agentmux_capability_run_command``.
A Bash call is not a mistake to retry, a permission to ask about, or a reason to
reach for another shell; it is a routing signal. This hook denies it and injects
the one instruction that fixes it.

The check reads ``raw_tool_name``, not ``tool_name``: hook_common aliases the
capability run_command tool to ``Bash`` so shell guards cover it, and aliasing
makes the two indistinguishable. Blocking on the alias would deny the very tool
this hook routes to.

Registered with ``on_failure = "block"``, so a hook that dies on its own input
still stops the Bash call rather than letting it through.

Fails open inside ``run_hook`` (a crash logs and exits 0); the config's
``on_failure = "block"`` is what turns that into a block at the harness.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))

from hook_common import Decision, HookEvent, run_hook

HOOK_NAME = "bash-tool-steer"

# Every harness spelling of the dead surface. Lowercase `bash` is what omp
# and Grok emit; `sh`/`zsh`/`shell`/`terminal`/`exec`/`run_terminal_cmd` are
# the spellings shell-denial-steer already recovers from after the fact, so
# this hook refuses them before they run. hook_common aliases some of these
# to Bash, which is why the check reads raw_tool_name: the alias of the
# capability run_command must pass, the harness shells must not.
BLOCKED_RAW_TOOL_NAMES = frozenset(
    {
        "Bash",
        "bash",
        "sh",
        "zsh",
        "shell",
        "terminal",
        "exec",
        "run_terminal_cmd",
        "run_terminal_command",
    }
)

DENY_REASON = (
    "Bash is disabled; use run_command. "
    "The Bash tool is dead surface on this machine — never call it, not once, "
    "not even for a bare `ls`. Run every command through "
    "mcp__capability__agentmux_capability_run_command "
    "(harnesses that prefix it show `mcp__capability__agentmux_capability_run_command`). "
    "If that tool is not in your tool list, call search_tools(\"command execution\") "
    "right then, before any other tool call. A failing run_command is fixed by "
    "rephrasing the command, never by switching shells."
)


def decide(event: HookEvent) -> Decision | None:
    if event.raw_tool_name not in BLOCKED_RAW_TOOL_NAMES:
        return None
    return Decision.deny(DENY_REASON, log_detail="bash-tool")


if __name__ == "__main__":
    run_hook(HOOK_NAME, decide)
