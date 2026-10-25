#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""PreToolUse (Agent|Task matcher) — subagent model guard.

For untyped (general-purpose) subagent spawns that carry no explicit model,
injects model=sonnet as the per-invocation override so the orchestrator's
expensive tier does not silently propagate to workers.

Grok Build is the exception: spawn_subagent rejects any explicit model
("Explicit subagent model selection is unavailable"). Injecting sonnet
there turns every worker spawn into a hard failure. Detect Grok via
GROK_SESSION_ID or the native tool name spawn_subagent, stay silent, and
leave Claude Code / Cursor / Codex injection unchanged.

Fails open on every edge case: parse errors, unexpected field shapes, or any
agent type that is not general-purpose/absent → exit 0, no output. Named
custom agents, haiku/opus-pinned agents, explore, and plan are all left
untouched.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))

from hook_common import Decision, HookEvent, run_hook

HOOK_NAME = "subagent-model-guard"
UNTYPED_SUBAGENT_TYPES = frozenset({"general-purpose", "claude", ""})
INJECTED_MODEL = "sonnet"
INJECT_REASON = f"subagent-model-guard: injecting model={INJECTED_MODEL} for untyped agent spawn"
INJECT_LOG_LABEL = "inject"
ABSENT_SUBAGENT_TYPE = "<absent>"
GROK_SPAWN_TOOL = "spawn_subagent"
GROK_SKIP_REASON = "subagent-model-guard: Grok Build rejects explicit model; skipping injection"


def is_grok_build(event: HookEvent, env: Mapping[str, str] | None = None) -> bool:
    """True for a Grok Build session or a native Grok spawn_subagent call."""
    lookup = os.environ if env is None else env
    if lookup.get("GROK_SESSION_ID"):
        return True
    return event.field("tool_name", "toolName") == GROK_SPAWN_TOOL


def decide(event: HookEvent, env: Mapping[str, str] | None = None) -> Decision | None:
    if event.tool_name not in ("Agent", "Task"):
        return None

    subagent_type = event.subagent_type
    if subagent_type not in UNTYPED_SUBAGENT_TYPES:
        return Decision.no_objection(f"typed spawn passthrough: {subagent_type}")

    if is_grok_build(event, env):
        return Decision.no_objection(GROK_SKIP_REASON)

    model = event.tool_input("model")
    if model:
        return Decision.no_objection(f"untyped spawn, explicit model already set: {model}")

    # Merged onto .tool_input only (never Grok's toolInput), as the .sh does.
    tool_input = event.payload.get("tool_input")
    updated_input = {
        **(tool_input if isinstance(tool_input, dict) else {}),
        "model": INJECTED_MODEL,
    }
    label = subagent_type or ABSENT_SUBAGENT_TYPE
    return Decision.allow(
        INJECT_REASON,
        updated_input=updated_input,
        log_label=INJECT_LOG_LABEL,
        log_detail=f"untyped spawn (subagent_type={label}) -> model={INJECTED_MODEL}",
    )


if __name__ == "__main__":
    run_hook(HOOK_NAME, decide)
