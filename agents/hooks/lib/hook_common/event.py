"""One hook invocation's stdin payload, in Claude Code or Grok shape."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

# Grok tool names normalized to Claude Code's, so one `match` serves both.
TOOL_NAME_ALIASES = {
    # run_command is the only shell runner the instructions allow, so the
    # prefix harnesses use for the capability must normalize like Bash.
    "mcp__capability__agentmux_capability_run_command": "Bash",
    "agentmux_capability_run_command": "Bash",
    "run_terminal_command": "Bash",
    "search_replace": "Edit",
    "write": "Write",
    "spawn_subagent": "Task",
    "terminal": "Bash",
    "write_file": "Write",
    "patch": "Edit",
    "delegate_task": "Task",
}

EVENT_NAME_ALIASES = {
    "post_tool_use": "PostToolUse",
    "post_tool_use_failure": "PostToolUseFailure",
    "pre_tool_use": "PreToolUse",
    "stop": "Stop",
    "pre_tool_call": "PreToolUse",
    "post_tool_call": "PostToolUse",
    "pre_llm_call": "UserPromptSubmit",
    "on_session_start": "SessionStart",
    "on_session_end": "SessionEnd",
    "pre_verify": "Stop",
    "post_llm_call": "Stop",
    "subagent_stop": "SubagentStop",
}

TOOL_INPUT_KEYS = ("tool_input", "toolInput")


def is_absent(value: Any) -> bool:
    """jq's notion of a missing value for ``//``: null or false."""
    return value is None or value is False


def as_text(value: Any) -> str:
    """jq ``-r`` rendering: absent is "", strings are raw, the rest is JSON."""
    if is_absent(value):
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value)


@dataclass(frozen=True, slots=True)
class HookEvent:
    """Field access with jq ``//`` semantics; every value comes back as text."""

    payload: Mapping[str, Any]

    @classmethod
    def parse(cls, raw: str) -> HookEvent | None:
        """None for empty, malformed, or non-object input — hooks fail open on it."""
        if not raw.strip():
            return None
        try:
            payload = json.loads(raw)
        except ValueError:
            return None
        return cls(payload) if isinstance(payload, dict) else None

    def field(self, snake: str, camel: str) -> str:
        """``.snake // .camel`` as text."""
        value = self.payload.get(snake)
        return as_text(self.payload.get(camel) if is_absent(value) else value)

    @property
    def tool_name(self) -> str:
        name = self.field("tool_name", "toolName")
        return TOOL_NAME_ALIASES.get(name, name)

    @property
    def raw_tool_name(self) -> str:
        """The harness spelling, before aliasing (``Bash`` vs the capability run_command)."""
        return self.field("tool_name", "toolName")

    @property
    def event_name(self) -> str:
        name = self.field("hook_event_name", "hookEventName")
        return EVENT_NAME_ALIASES.get(name, name)

    @property
    def session_id(self) -> str:
        return self.field("session_id", "sessionId")

    @property
    def subagent_type(self) -> str:
        """``.tool_input.subagent_type // .toolInput.subagentType``.

        Grok renames the key as well as the section, so tool_input(name)
        alone misses it.
        """
        return self.tool_input("subagent_type") or as_text(
            self._section_value("toolInput", "subagentType")
        )

    def tool_input(self, name: str) -> str:
        """``.tool_input[name] // .toolInput[name]`` as text ("" when absent).

        A present empty string wins over the other section, as in jq.
        """
        for key in TOOL_INPUT_KEYS:
            value = self._section_value(key, name)
            if not is_absent(value):
                return as_text(value)
        if name == "file_path":
            for key in TOOL_INPUT_KEYS:
                value = self._section_value(key, "path")
                if not is_absent(value):
                    return as_text(value)
        return ""

    def tool_input_section(self) -> dict[str, Any]:
        """``.tool_input // .toolInput // {}`` — the raw object, for updatedInput merges."""
        for key in TOOL_INPUT_KEYS:
            section = self.payload.get(key)
            if isinstance(section, dict):
                return section
        return {}

    def _section_value(self, section_key: str, name: str) -> Any:
        section = self.payload.get(section_key)
        return section.get(name) if isinstance(section, dict) else None
