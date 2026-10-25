#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""PreToolUse (Agent|Task matcher) — structured work-order gate.

Port of work-order-gate.sh (its header keeps the full design rationale).
Every Agent/Task prompt must open with a fenced ```yaml work_order block,
validated and compiled by lib/work-order-compile.py; the compiled prompt
replaces the original through updatedInput.

A spawn walks: fork exemption -> repair-by-reference restore
(lib/work_order_repair) -> worktree target queued (before validation, so a
cancelled gate still provisions the right repo; dropped again on deny) ->
fence required (legacy prose passes until LEGACY_COMPAT_DEADLINE) ->
compile. Deny reasons are built by lib/work_order_denials.

Fails OPEN on every edge case: missing uv, an unrunnable compile script, a
compiler timeout or odd output, or any tool other than Agent/Task -> silent.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))

import work_order_denials as denials
import worktree_target_queue
from hook_common import Clock, Decision, HookEvent, HookSettings, run_hook
from work_order_compiler import WorkOrderCompiler, compile_envelope
from work_order_repair import (
    PendingOrders,
    PendingState,
    has_main_fence,
    merge_resend,
    order_ref_of,
    resend_body,
    resend_order_ref,
)

HOOK_NAME = "work-order-gate"
SPAWN_TOOLS = frozenset({"Agent", "Task"})
FORK_SUBAGENT_TYPE = "fork"
WORKTREE_ISOLATION = "worktree"
ABSENT_LABEL = "<absent>"
ORDERS_DIR_NAME = "work-orders"
EDIT_SUBAGENT_TYPES = frozenset(
    {"implement", "mechanical-refactor", "build-break-fixer"}
)

# 2026-09-16 (ship date) + 14 days. A prompt with only legacy markers and no
# fence still passes, warning-only, until this date; required after.
LEGACY_COMPAT_DEADLINE = "2026-09-30"
DONE_WHEN_PATTERN = re.compile(r"done[- ]when|done\.condition|Done when", re.IGNORECASE)
TURN_CAP_PATTERN = re.compile(r"turn cap|turn limit", re.IGNORECASE)
TOKEN_BUDGET_PATTERN = re.compile(r"token budget|~?[0-9]+k tokens", re.IGNORECASE)
BLAST_RADIUS_PATTERN = re.compile(
    r"blast[- ]radius|do not (touch|modify|edit)|read[- ]only", re.IGNORECASE
)


@dataclass(frozen=True, slots=True)
class Spawn:
    """The Agent/Task call's fields, read once."""

    subagent_type: str
    prompt: str
    isolation: str
    harness_worktree_isolation: str
    model: str
    cwd: str
    session_id: str
    scratchpad_dir: str
    tool_input: dict[str, Any]

    @classmethod
    def from_event(cls, event: HookEvent) -> Spawn:
        return cls(
            subagent_type=event.subagent_type,
            prompt=event.tool_input("prompt"),
            isolation=event.tool_input("isolation"),
            # Harness-declared: Hermes creates a worktree per child
            # (delegation.worktree_isolation) and has no per-call isolation
            # parameter; the payload flag is the only signal the policy can trust.
            harness_worktree_isolation=event.field(
                "harness_worktree_isolation", "harnessWorktreeIsolation"
            ),
            model=event.tool_input("model"),
            cwd=event.field("cwd", "cwd") or os.getcwd(),
            session_id=event.session_id,
            scratchpad_dir=event.field("scratchpad_dir", "scratchpadDir"),
            tool_input=event.tool_input_section(),
        )

    @property
    def effective_isolation(self) -> str:
        """The isolation boundary the harness actually provides: an explicit
        per-call isolation, else the harness-declared per-child worktree."""
        return self.isolation or (
            WORKTREE_ISOLATION if self.harness_worktree_isolation else ""
        )

    @property
    def label(self) -> str:
        return self.subagent_type or ABSENT_LABEL

    @property
    def is_edit_type(self) -> bool:
        return self.subagent_type in EDIT_SUBAGENT_TYPES


def carries_legacy_markers(prompt: str, is_edit_type: bool) -> bool:
    """The pre-fence prose protocol: done-when, turn cap, token budget (+ blast radius for editors)."""
    patterns = [DONE_WHEN_PATTERN, TURN_CAP_PATTERN, TOKEN_BUDGET_PATTERN]
    if is_edit_type:
        patterns.append(BLAST_RADIUS_PATTERN)
    return all(pattern.search(prompt) for pattern in patterns)


def before_legacy_deadline(clock: Clock) -> bool:
    return clock.now_iso()[:10].replace("-", "") < LEGACY_COMPAT_DEADLINE.replace(
        "-", ""
    )


class GateRun:
    """One spawn's walk through the gate: the prompt may be rebuilt from a
    stored order, and a queued worktree target must be dropped on deny."""

    def __init__(
        self,
        spawn: Spawn,
        settings: HookSettings,
        compiler: WorkOrderCompiler,
        clock: Clock,
    ) -> None:
        self.spawn = spawn
        self.settings = settings
        self.orders_dir = settings.state_dir / ORDERS_DIR_NAME
        self.pending = PendingOrders(self.orders_dir)
        self.compiler = compiler
        self.clock = clock
        self.prompt = spawn.prompt
        self.repair_ref = ""
        self.worktree_record: Path | None = None

    def decide(self) -> Decision | None:
        stale_ref = self._restore_repair()
        if stale_ref is not None:
            return stale_ref
        envelope = self._envelope()
        self._queue_worktree_target(envelope)
        if not has_main_fence(self.prompt):
            return self._without_fence()
        return self._compile(envelope)

    def _deny(self, reason: str) -> Decision:
        if self.worktree_record is not None:
            with contextlib.suppress(OSError):
                self.worktree_record.unlink()
            self.worktree_record = None
        detail = f"subagent_type={self.spawn.label}: " + reason.replace("\n", " ")
        return Decision.deny(reason, log_detail=detail)

    def _examples_dir(self) -> Path:
        return self.pending.examples_directory

    def _deny_repairable(self, extra: dict[str, Any]) -> Decision:
        """Store the (merged) prompt under a stable ref, reused across a chain of repairs."""
        ref = self.repair_ref or order_ref_of(self.spawn.prompt)
        self.pending.store(ref, self.prompt)
        return self._deny(
            denials.repairable_reason(ref, self.prompt, extra, self._examples_dir())
        )

    def _deny_fresh_order(self, extra: dict[str, Any]) -> Decision:
        """Unparsed YAML can't take a patch (ZYS-737): nothing stored, any pending ref dropped."""
        if self.repair_ref:
            self.pending.discard(self.repair_ref)
        return self._deny(
            denials.fresh_order_reason(self.prompt, extra, self._examples_dir())
        )

    def _deny_policy(self, extra: dict[str, Any]) -> Decision:
        """A rule the order breaks, not a field it lacks: a patch can't fix it, so nothing is stored."""
        if self.repair_ref:
            self.pending.discard(self.repair_ref)
        return self._deny(denials.policy_reason(extra["errors"]))

    def _restore_repair(self) -> Decision | None:
        """Rebuild the prompt a resend refers to; a deny if the ref can't be used."""
        ref = resend_order_ref(self.prompt)
        if ref is None:
            return None
        found = self.pending.lookup(ref, self.clock.now_epoch())
        match found.state:
            case PendingState.UNKNOWN:
                return self._deny(
                    denials.stale_ref_reason(
                        ref, denials.STALE_UNKNOWN, self._examples_dir()
                    )
                )
            case PendingState.EXPIRED:
                return self._deny(
                    denials.stale_ref_reason(
                        ref, denials.STALE_EXPIRED, self._examples_dir()
                    )
                )
        self.prompt = merge_resend(found.prompt, resend_body(self.prompt))
        self.repair_ref = ref
        return None

    def _envelope(self) -> str:
        spawn = self.spawn
        return compile_envelope(
            {
                "prompt": self.prompt,
                "isolation": spawn.effective_isolation,
                "model": spawn.model,
                "cwd": spawn.cwd,
                "scratchpad_dir": spawn.scratchpad_dir,
                "is_edit_type": spawn.is_edit_type,
                "harness_worktree_isolation": spawn.harness_worktree_isolation,
            }
        )

    def _queue_worktree_target(self, envelope: str) -> None:
        # Only an EXPLICIT per-call isolation: isolation: "worktree" means the
        # WorktreeCreate provisioner will create the tree. A harness-declared
        # worktree (Hermes delegation.worktree_isolation) is created by the
        # harness itself — it never fires WorktreeCreate — so it must not
        # enqueue, or the record would linger and misroute a later spawn.
        if self.spawn.isolation != WORKTREE_ISOLATION:
            return
        self.worktree_record = worktree_target_queue.enqueue(
            self.settings.state_dir,
            self.spawn.session_id,
            envelope,
            self.clock.now_epoch(),
        )

    def _without_fence(self) -> Decision:
        if carries_legacy_markers(
            self.prompt, self.spawn.is_edit_type
        ) and before_legacy_deadline(self.clock):
            return Decision.no_objection(
                f"legacy-prose-compat subagent_type={self.spawn.label} deadline={LEGACY_COMPAT_DEADLINE}"
            )
        return self._deny_repairable(denials.missing_fence_fields())

    def _compile(self, envelope: str) -> Decision | None:
        verdict = self.compiler.compile(envelope)
        if verdict is None:
            return None
        if verdict.get("ok") is not True:
            extra = {"errors": verdict.get("errors", [])}
            if denials.policy_errors(extra["errors"]):
                return self._deny_policy(extra)
            if verdict.get("repairable") is False:
                return self._deny_fresh_order(extra)
            return self._deny_repairable(extra)

        if self.repair_ref:
            self.pending.discard(self.repair_ref)
        order_id = verdict.get("order_id", "")
        self._record_order(order_id, verdict)
        return Decision.allow(
            f"work-order-gate: compiled and validated, order_id={order_id}",
            updated_input={
                **self.spawn.tool_input,
                "prompt": verdict.get("compiled_prompt", ""),
            },
            log_detail=f"subagent_type={self.spawn.label} order_id={order_id}",
        )

    def _record_order(self, order_id: str, verdict: dict[str, Any]) -> None:
        """work-order-verify reads this back at SubagentStop (``jq 'del(.compiled_prompt)'`` output)."""
        record = {
            key: value for key, value in verdict.items() if key != "compiled_prompt"
        }
        with contextlib.suppress(OSError):
            self.orders_dir.mkdir(parents=True, exist_ok=True)
            (self.orders_dir / f"{order_id}.json").write_text(
                json.dumps(record, indent=2, ensure_ascii=False) + "\n"
            )


def decide(event: HookEvent) -> Decision | None:
    if event.tool_name not in SPAWN_TOOLS:
        return None
    compiler = WorkOrderCompiler.from_env()
    if not compiler.is_runnable():
        return None
    spawn = Spawn.from_event(event)
    if spawn.subagent_type == FORK_SUBAGENT_TYPE:
        return Decision.no_objection("fork-exempt")
    return GateRun(spawn, HookSettings.from_env(), compiler, Clock.from_env()).decide()


if __name__ == "__main__":
    run_hook(HOOK_NAME, decide)
