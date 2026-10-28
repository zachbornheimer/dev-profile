"""ZYS-1758 CoS ruling 3, tripwire slice: the hook-skip guard refuses both incident
commands in every raw omp / Claude run_command shape and in omp `eval` code.

Ported from the box staging test test_agent_session_shapes_zys1758.py without its
Agent-Session trailer half (decision 4, not part of this landing).

Raw shapes, from the Mac evidence:
- Claude-format PreToolUse for MCP run_command: tool_name
  `mcp__capability__agentmux_capability_run_command`, tool_input {command}.
- omp direct MCP call: toolName/tool_name `mcp__capability_agentmux_capability_run_command`
  (one underscore), tool_input {command, cwd, purpose, timeout_seconds}.
- omp eval (ManagerialBooby): language "py", a `sh(c, cwd=...)` helper that runs
  subprocess.run(c, shell=True), then `print(sh('git ...'))`.

The two incident commands: the ShallowPelican `git push --no-verify origin main` and
the f4bd6e86 `HK=0 git commit`.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest
import tomllib
from hook_harness import HOOKS_DIR, HookRunner

TRIPWIRE = "gate-bypass-tripwire.py"
SID = "01a17553-7563-72cf-be2e-80628fa41ab7"

PUSH = "cd /Users/x/.worktrees/capability-replicas-zys-1731 && git push --no-verify origin main 2>&1 | tail -4 && git rev-parse origin/main"
HK0 = "cd /Users/x/capability-replicas && HK=0 git commit -m \"$(cat <<'EOF'\nfix: x\nEOF\n)\" -- a.ts"
INCIDENTS = {"no-verify-push": PUSH, "hk0-commit": HK0}

SH_HELPER = (
    "import subprocess,os\n"
    "def sh(c,cwd='{cwd}'):\n"
    "    r=subprocess.run(c,shell=True,cwd=cwd,capture_output=True,text=True);return r.stdout+r.stderr\n"
)


def claude_mcp(command: str) -> dict[str, Any]:
    return {
        "cwd": "/private/tmp/w",
        "hook_event_name": "PreToolUse",
        "model": "claude-opus-5",
        "permission_mode": "bypassPermissions",
        "session_id": SID,
        "tool_input": {"command": command},
        "tool_name": "mcp__capability__agentmux_capability_run_command",
        "tool_use_id": "toolu_01JAx3Ty44fAT3uWiD38nWG9",
        "transcript_path": f"/Users/x/.claude/projects/-tmp/{SID}.jsonl",
    }


def omp_mcp(
    command: str, server: str = "mcp__capability_agentmux_capability_run_command"
) -> dict[str, Any]:
    tool_input = {
        "command": command,
        "cwd": "/tmp",
        "purpose": "x",
        "timeout_seconds": 290,
    }
    return {
        "type": "tool_call",
        "hook_event_name": "PreToolUse",
        "session_id": SID,
        "toolCallId": "toolu_01JAx3Ty44fAT3uWiD38nWG9",
        "toolName": server,
        "tool_name": server,
        "input": tool_input,
        "tool_input": tool_input,
    }


def omp_eval(code: str, language: str = "py") -> dict[str, Any]:
    return {
        "hook_event_name": "PreToolUse",
        "session_id": SID,
        "tool_name": "eval",
        "toolName": "eval",
        "tool_input": {"language": language, "code": code},
    }


def eval_sh(command: str, cwd: str = "/Users/x/capability-replicas") -> dict[str, Any]:
    """The ManagerialBooby shape: a `sh()` helper, then print(sh('<command>'))."""
    return omp_eval(SH_HELPER.format(cwd=cwd) + f"print(sh({command!r}))")


# --- hook-skip guards: the tripwire refuses both incidents in every raw shape ---

GUARD_CASES: dict[str, tuple[dict[str, Any], str]] = {}
for _name, _cmd in INCIDENTS.items():
    GUARD_CASES[f"claude-mcp-{_name}"] = (claude_mcp(_cmd), "deny")
    GUARD_CASES[f"omp-mcp-{_name}"] = (omp_mcp(_cmd), "deny")
    GUARD_CASES[f"omp-mcp-always-on-{_name}"] = (
        omp_mcp(_cmd, "mcp__capability_always_on_agentmux_capability_run_command"),
        "deny",
    )
    GUARD_CASES[f"omp-eval-sh-{_name}"] = (eval_sh(_cmd), "deny")
    GUARD_CASES[f"native-brief-double-{_name}"] = (
        omp_mcp(_cmd, "mcp__capability_agentmux__capability_run_command"),
        "deny",
    )
GUARD_CASES.update(
    {
        "omp-eval-argv-no-verify": (
            omp_eval(
                "import subprocess\nsubprocess.run(['git', 'push', '--no-verify', 'origin', 'main'])"
            ),
            "deny",
        ),
        "omp-eval-env-dict-hk0": (
            omp_eval(
                "import subprocess,os\nsubprocess.run('git commit -m x', shell=True, env={**os.environ, 'HK': '0'})"
            ),
            "deny",
        ),
        "omp-eval-environ-hk0": (
            omp_eval(
                "import os\nos.environ['HK'] = '0'\n"
                + SH_HELPER.format(cwd="/r")
                + "print(sh('git commit -m x'))"
            ),
            "deny",
        ),
        "omp-eval-js-no-verify": (
            omp_eval(
                "const r = await $`git push --no-verify origin main`;", language="js"
            ),
            "deny",
        ),
        "omp-eval-sh-plain": (
            eval_sh("git status --short | head -20; git branch --show-current"),
            "none",
        ),
        "omp-eval-read-only": (omp_eval("print(open('/tmp/x').read())"), "none"),
        "claude-mcp-plain": (claude_mcp("git log --oneline -3"), "none"),
        "omp-mcp-plain": (omp_mcp("git push -u origin zys-1731"), "none"),
    }
)


@pytest.mark.parametrize("name", sorted(GUARD_CASES))
def test_tripwire_raw_shapes(hooks: HookRunner, name: str) -> None:
    payload, want = GUARD_CASES[name]
    run = hooks.run_payload(TRIPWIRE, payload)
    assert run.exit_code == 0 and not run.failed_open, run.log
    assert run.decision == want, f"{name} -> {run.stdout}"


def _hooks_toml() -> dict[str, Any]:
    path = os.environ.get("ZYS1758_HOOKS_TOML") or str(
        HOOKS_DIR.parents[1] / "apps/agent-hooks/hooks.toml"
    )
    return tomllib.loads(Path(path).read_text())


def _matcher(row: str) -> set[str]:
    return set(
        next(r for r in _hooks_toml()["hooks"] if r["name"] == row)["matcher"].split(
            "|"
        )
    )


def test_rows_match_every_raw_run_command_name() -> None:
    names = {
        "mcp__capability__agentmux_capability_run_command",
        "mcp__capability_agentmux_capability_run_command",
        "mcp__capability_always_on_agentmux_capability_run_command",
        # The brief's spelling (double underscore after agentmux): absent from the
        # evidence, but a native tool name of that form reached no tripwire row on
        # the Mac (level-1 containment payloads 11-12, 2026-10-27).
        "mcp__capability_agentmux__capability_run_command",
        "eval",
    }
    assert names <= _matcher("pretooluse-gate-bypass-tripwire")
