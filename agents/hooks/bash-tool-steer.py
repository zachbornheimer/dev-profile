#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""PreToolUse (foreign shells) — a shell tool omp does not own is a routing signal.

In omp every command runs through the native lowercase ``bash`` tool, extended by
``extensions/bash-rules.ts``. ``run_command`` was retired on 2026-11-16 and no longer
exists; a note that still names it is stale. The names denied here are the other
harnesses' shells (capital ``Bash``, ``sh``, ``zsh``, ``shell``, ``terminal``, ``exec``,
``run_terminal_*``). Calling one is not a mistake to retry, a permission to ask about, or
a reason to reach for another shell. This hook denies it and injects the one instruction
that fixes it.

The check reads ``raw_tool_name``, not ``tool_name``: hook_common aliases some shell names
to ``Bash`` so shell guards cover them, and aliasing makes them indistinguishable.
Lowercase ``bash`` is omp's own shell and is never denied here.

Registered with ``on_failure = "block"``, so a hook that dies on its own input
still stops the call rather than letting it through.

Fails open inside ``run_hook`` (a crash logs and exits 0); the config's
``on_failure = "block"`` is what turns that into a block at the harness.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))

from hook_common import Decision, HookEvent, run_hook

HOOK_NAME = "bash-tool-steer"

# Every other harness's spelling of a shell. Lowercase `bash` is omp's native shell and is
# deliberately absent. `sh`/`zsh`/`shell`/`terminal`/`exec`/`run_terminal_cmd` are the
# spellings shell-denial-steer already recovers from after the fact, so this hook refuses
# them before they run.
BLOCKED_RAW_TOOL_NAMES = frozenset(
    {
        "Bash",
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
    "That shell tool is not the one on this machine; use omp's native `bash` tool. "
    "Run every command through `bash`, extended by extensions/bash-rules.ts: each refusal "
    "names the native tool or command that works. `run_command` was retired on "
    "2026-11-16, so any note that names it is stale. If `bash` is missing from your tool "
    'list, call tool_search { query: "run a shell command" } right then, before any other '
    "tool call. A failing `bash` call is fixed by rephrasing the command, never by "
    "switching shells."
)


def decide(event: HookEvent) -> Decision | None:
    if event.raw_tool_name not in BLOCKED_RAW_TOOL_NAMES:
        return None
    return Decision.deny(DENY_REASON, log_detail="foreign-shell")


if __name__ == "__main__":
    run_hook(HOOK_NAME, decide)
