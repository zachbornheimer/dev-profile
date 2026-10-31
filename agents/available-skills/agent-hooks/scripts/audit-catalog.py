#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Audit an agent-hooks catalog for faults `agent-hooks validate` accepts silently.

Usage: audit-catalog.py [hooks.toml]      (default ~/.config/agent-hooks/hooks.toml)

Run `agent-hooks validate` first: it rejects malformed TOML, bad versions, group cycles and name clashes with clear
errors. This script audits ONE file; it does not see cross-file replacement (user file vs ./hooks.toml).
Exit: 0 clean/WARN only, 1 any ERROR, 2 unreadable or malformed input.

Prints one `LEVEL  hook-name  message` line per finding and exits 1 if any ERROR.
`validate` passes all of these; the dispatcher then skips, replaces, or ignores them.

ERROR: hook never runs or silently replaced something.
WARN:  probably wrong, check by hand.
"""

from __future__ import annotations

import collections
import os
import re
import shlex
import sys
from pathlib import Path

import tomllib

# HookSpec fields in src/config.rs. Anything else (enabled, async, script, policy, ...) is ignored.
KNOWN_KEYS = {
    "name",
    "command",
    "events",
    "agents",
    "timeout",
    "protocol",
    "provides",
    "on_failure",
    "shell",
    "matcher",
    "env",
}
# Canonical names (src/events.rs) plus the native spellings the dispatcher normalizes or passes through.
KNOWN_EVENTS = {
    "session.start",
    "session.end",
    "prompt.submit",
    "tool.before",
    "tool.after",
    "turn.stop",
    "permission.request",
    "context.compact.before",
    "context.compact.after",
    "subagent.start",
    "subagent.stop",
    "worktree.create",
    "worktree.remove",
    "SessionStart",
    "SessionEnd",
    "UserPromptSubmit",
    "PreToolUse",
    "PostToolUse",
    "Stop",
    "PermissionRequest",
    "PreCompact",
    "PostCompact",
    "SubagentStart",
    "SubagentStop",
    "WorktreeCreate",
    "WorktreeRemove",
    "BeforeAgent",
    "AfterAgent",
    "BeforeTool",
    "AfterTool",
    "PreCompress",
    "BeforeModel",
    "AfterModel",
    "sessionStart",
    "sessionEnd",
    "userPromptSubmitted",
    "preToolUse",
    "postToolUse",
    "agentStop",
    "preCompact",
    "errorOccurred",
    "on_session_start",
    "on_session_end",
    "pre_llm_call",
    "post_llm_call",
    "pre_tool_call",
    "post_tool_call",
    "pre_verify",
    "agent_loop_stopped",
    "on_human_input_resolved",
    "subagent_start",
    "subagent_stop",
    # Claude-only pass-through names
    "Notification",
    "ElicitationResult",
    "StopFailure",
    "PostToolUseFailure",
    "Setup",
    "PermissionDenied",
    "UserPromptExpansion",
}
# AgentId::parse accepts these aliases, case-insensitively, after trimming.
AGENTS = {
    "claude",
    "claude-code",
    "codex",
    "gemini",
    "gemini-cli",
    "grok",
    "grok-build",
    "hermes",
    "copilot",
    "github-copilot",
    "opencode",
    "open-code",
    "mastra",
}
# humantime accepts many unit spellings and spaces; only reject strings with no number+unit shape at all.
DURATION = re.compile(r"^\s*(\d+(\.\d+)?\s*[a-zA-Zµμ]+\s*)+$")
# Events whose payload carries a matcher-able field (tool name, source, trigger, ...).
MATCHABLE = {
    "tool.before",
    "tool.after",
    "permission.request",
    "session.start",
    "session.end",
    "context.compact.before",
    "context.compact.after",
    "subagent.start",
    "subagent.stop",
    "PreToolUse",
    "PostToolUse",
    "PermissionRequest",
    "SessionStart",
    "SessionEnd",
    "PreCompact",
    "PostCompact",
    "SubagentStart",
    "SubagentStop",
    "BeforeTool",
    "AfterTool",
    "PreCompress",
    "preToolUse",
    "postToolUse",
    "pre_tool_call",
    "post_tool_call",
    "Notification",
    "PostToolUseFailure",
    "PermissionDenied",
}
SHELLS = {"sh", "bash", "zsh", "dash", "ksh"}
REGEXY_MATCHER = re.compile(r"\.\*|\w\*|[\[\](){}^$+?\\]")


def audit(path: Path) -> list[tuple[str, str, str]]:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    hooks = data.get("hooks", [])
    groups = data.get("groups", {})
    shell_default = data.get("defaults", {}).get("shell", False)
    found: list[tuple[str, str, str]] = []

    def add(level: str, name: str, message: str) -> None:
        found.append((level, name, message))

    for name, count in collections.Counter(h.get("name") for h in hooks).items():
        if count > 1:
            add(
                "ERROR",
                str(name),
                f"{count} rows share this name; the last silently replaces the others",
            )
    for name in groups:
        if any(h.get("name") == name for h in hooks):
            add("ERROR", name, "group has the same name as a hook")
    names = {h.get("name") for h in hooks}
    for group, members in groups.items():
        for member in members:
            if member not in names and member not in groups:
                add("WARN", group, f"group member {member!r} is not a hook or group")

    for hook in hooks:
        name = str(hook.get("name"))
        command = hook.get("command")
        if not command:
            extra = [k for k in ("policy", "script") if k in hook]
            add(
                "ERROR",
                name,
                "no command: skipped silently, never runs"
                + (f" (has {extra[0]}=, which is ignored)" if extra else ""),
            )
        for key in sorted(set(hook) - KNOWN_KEYS):
            if key not in ("policy", "script"):
                add("WARN", name, f"unknown key {key!r} is ignored")
        for event in hook.get("events", []):
            if event not in KNOWN_EVENTS:
                add(
                    "WARN",
                    name,
                    f"event {event!r} is not a known canonical or native name",
                )
        if not hook.get("events"):
            add(
                "WARN",
                name,
                "empty events: runs on any event when named, never via an event selector",
            )
        for agent in hook.get("agents", []):
            if str(agent).strip().lower() not in AGENTS:
                add("ERROR", name, f"unknown agent {agent!r}")
        timeout = hook.get("timeout")
        if timeout is not None and not DURATION.match(str(timeout).strip()):
            add("ERROR", name, f"timeout {timeout!r} is not a humantime duration")
        matcher = hook.get("matcher")
        if matcher and REGEXY_MATCHER.search(matcher):
            add(
                "ERROR",
                name,
                f"matcher {matcher!r} looks like a regex; matchers are exact names split on | or ,",
            )
        if (
            matcher
            and matcher.strip() != "*"
            and "*" in matcher
            and not REGEXY_MATCHER.search(matcher)
        ):
            add(
                "ERROR",
                name,
                f"matcher {matcher!r}: `*` only means match-all when it is the whole matcher",
            )
        events = hook.get("events", [])
        if (
            matcher
            and matcher.strip() not in ("", "*")
            and events
            and not any(e in MATCHABLE for e in events)
        ):
            add(
                "WARN",
                name,
                f"matcher set but {events} carry no tool/source/trigger field; it will never match",
            )
        if command:
            parts = [command] if isinstance(command, str) else list(command)
            shell = hook.get("shell", shell_default)
            if shell and len(parts) > 1:
                shellish = os.path.basename(parts[0]) in SHELLS and any(
                    re.fullmatch(r"-[a-z]*c", p) for p in parts[1:3]
                )
                if shellish:
                    add(
                        "ERROR",
                        name,
                        "shell=true with [shell, -c, ...] becomes `sh -c <shell> -c ...`; put the whole command in element 0",
                    )
                else:
                    add(
                        "WARN",
                        name,
                        "shell=true: items after element 0 become $0/$1 of `sh -c`, NOT arguments; put arguments inside the command string",
                    )
            program = parts[0]
            if shell:
                try:
                    tokens = shlex.split(program)
                except ValueError:
                    tokens = program.split()
                tokens = [
                    t
                    for t in tokens
                    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", t)
                ]
                program = tokens[0] if tokens else ""
            elif program.startswith(("~", "$")):
                add(
                    "ERROR",
                    name,
                    f"shell=false does not expand {program!r}; spawn fails (use an absolute path or shell=true)",
                )
                continue
            elif len(parts) == 1 and " " in program and not Path(program).exists():
                add(
                    "ERROR",
                    name,
                    "shell=false with a single string that is a command plus arguments is one program name and fails to spawn",
                )
                continue
            if program.startswith(("/", "~", "$HOME")):
                resolved = Path(os.path.expandvars(os.path.expanduser(program)))
                if not resolved.exists():
                    add("ERROR", name, f"script {program} does not exist")
                elif not os.access(resolved, os.X_OK):
                    add("ERROR", name, f"script {program} is not executable")
    return found


def main(argv: list[str]) -> int:
    path = (
        Path(argv[1])
        if len(argv) > 1
        else Path.home() / ".config/agent-hooks/hooks.toml"
    )
    try:
        findings = audit(path)
    except (
        OSError,
        tomllib.TOMLDecodeError,
        TypeError,
        AttributeError,
        ValueError,
    ) as exc:
        print(
            f"cannot audit {path}: {type(exc).__name__}: {exc} (run `agent-hooks validate` first)",
            file=sys.stderr,
        )
        return 2
    for level, name, message in findings:
        print(f"{level:5}  {name}  {message}")
    print(f"{len(findings)} finding(s) in {path}", file=sys.stderr)
    return 1 if any(level == "ERROR" for level, _, _ in findings) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
