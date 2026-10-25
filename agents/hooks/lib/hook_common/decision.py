"""What a hook concluded, and its stdout JSON (byte-identical to ``jq -n``)."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any

ALLOW_LOG_LABEL = "allow"
PRE_TOOL_USE = "PreToolUse"


class DecisionKind(Enum):
    NO_OBJECTION = "no-objection"  # logged, nothing on stdout
    ALLOW = "allow"  # explicit permissionDecision:"allow"
    DENY = "deny"
    BLOCK = "block"  # Stop-style decision:"block"
    CONTEXT = "context"  # additionalContext, non-blocking


@dataclass(frozen=True, slots=True)
class Decision:
    """Build one with the classmethods, never directly.

    ``message`` is what the model reads; ``log_detail`` is what hooks.log
    records. They are the same text unless a .sh logged a shorter detail
    (a signature, a counter) than the reason it printed — pass
    ``log_detail=`` to keep that log line byte-identical.
    """

    kind: DecisionKind
    message: str
    log_label: str
    event_name: str = PRE_TOOL_USE
    log_detail: str | None = None
    updated_input: Mapping[str, Any] | None = None

    @classmethod
    def no_objection(cls, detail: str, log_label: str = ALLOW_LOG_LABEL) -> Decision:
        """Silent on stdout; logs ``log_label`` + ``detail`` (e.g. "recorded")."""
        return cls(DecisionKind.NO_OBJECTION, detail, log_label)

    @classmethod
    def allow(
        cls,
        reason: str,
        *,
        updated_input: Mapping[str, Any] | None = None,
        log_label: str = ALLOW_LOG_LABEL,
        log_detail: str | None = None,
    ) -> Decision:
        """Explicit allow; ``updated_input`` rewrites the tool call's input."""
        return cls(
            DecisionKind.ALLOW,
            reason,
            log_label,
            log_detail=log_detail,
            updated_input=updated_input,
        )

    @classmethod
    def deny(cls, reason: str, *, log_detail: str | None = None) -> Decision:
        return cls(DecisionKind.DENY, reason, "deny", log_detail=log_detail)

    @classmethod
    def block(cls, reason: str) -> Decision:
        return cls(DecisionKind.BLOCK, reason, "block", event_name="Stop")

    @classmethod
    def context(
        cls,
        text: str,
        event_name: str,
        log_label: str = ALLOW_LOG_LABEL,
        *,
        log_detail: str | None = None,
    ) -> Decision:
        return cls(
            DecisionKind.CONTEXT, text, log_label, event_name=event_name, log_detail=log_detail
        )

    @property
    def logged_detail(self) -> str:
        """The hooks.log detail column."""
        return self.message if self.log_detail is None else self.log_detail

    def to_json(self) -> str | None:
        """The stdout payload, formatted exactly as ``jq -n`` would; None if silent."""
        body: dict[str, Any]
        match self.kind:
            case DecisionKind.NO_OBJECTION:
                return None
            case DecisionKind.ALLOW | DecisionKind.DENY:
                specific: dict[str, Any] = {
                    "hookEventName": self.event_name,
                    "permissionDecision": self.kind.value,
                    "permissionDecisionReason": self.message,
                }
                if self.updated_input is not None:
                    specific["updatedInput"] = dict(self.updated_input)
                body = {"hookSpecificOutput": specific}
            case DecisionKind.BLOCK:
                body = {"decision": "block", "reason": self.message}
            case DecisionKind.CONTEXT:
                body = {
                    "hookSpecificOutput": {
                        "hookEventName": self.event_name,
                        "additionalContext": self.message,
                    }
                }
        return json.dumps(body, indent=2, ensure_ascii=False)
