#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""PreToolUse (Agent|Task matcher) — subagent model guard.

For untyped (general-purpose) subagent spawns that carry no explicit model,
injects model=sonnet as the per-invocation override so the orchestrator's
expensive tier does not silently propagate to workers.

Fails open on every edge case: parse errors, unexpected field shapes, or any
agent type that is not general-purpose/absent → exit 0, no output. Named
custom agents, haiku/opus-pinned agents, explore, and plan are all left
untouched.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))

from hook_common import Decision, HookEvent, run_hook

HOOK_NAME = "subagent-model-guard"
UNTYPED_SUBAGENT_TYPES = frozenset({"general-purpose", ""})
INJECTED_MODEL = "sonnet"
INJECT_REASON = (
    f"subagent-model-guard: injecting model={INJECTED_MODEL} for untyped agent spawn"
)
INJECT_LOG_LABEL = "inject"
ABSENT_SUBAGENT_TYPE = "<absent>"


def decide(event: HookEvent) -> Decision | None:
    if event.tool_name not in ("Agent", "Task"):
        return None

    subagent_type = event.subagent_type
    if subagent_type not in UNTYPED_SUBAGENT_TYPES:
        return Decision.no_objection(f"typed spawn passthrough: {subagent_type}")

    model = event.tool_input("model")
    if model:
        return Decision.no_objection(
            f"untyped spawn, explicit model already set: {model}"
        )

    # Merged onto .tool_input only.
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
