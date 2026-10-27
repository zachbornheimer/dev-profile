"""ZYS-1758: hook-skip paths the tripwire must refuse, and the wiring that makes it run.

Red before the fix: env-var hook switches (hk/husky/lefthook), persistent
`git config` hook disables, nested `sh -c`, the push helper that hardcodes
--no-verify, a script written to disk that pushes with --no-verify, and the
hooks.toml rows that named the tripwire by `policy=` only (so dispatch skipped
them and the guard never ran).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest
import tomllib
from hook_harness import HookRunner

PY_HOOK = "gate-bypass-tripwire.py"
DENY = "deny"
SILENT = "none"


def _bash(command: str) -> dict[str, Any]:
    return {"tool_name": "Bash", "tool_input": {"command": command}}


def _write(path: str, content: str) -> dict[str, Any]:
    return {"tool_name": "Write", "tool_input": {"file_path": path, "content": content}}


BASH_CASES: dict[str, tuple[str, str]] = {
    # the incident shapes
    "push-no-verify-to-main": ("git push --no-verify origin HEAD:main", DENY),
    "push-no-verify-quiet-lease": (
        'git push --quiet --no-verify --force-with-lease="refs/heads/main" origin x:refs/heads/main',
        DENY,
    ),
    # env-var hook switches
    "hk-zero-prefix": ("HK=0 git push origin main", DENY),
    "hk-false-prefix": ("HK=false git commit -m wip", DENY),
    "hk-zero-export": ("export HK=0; git push", DENY),
    "hk-zero-env": ("env HK=0 git push origin main", DENY),
    "hk-skip-hook": ("HK_SKIP_HOOK=pre-push git push", DENY),
    "hk-skip-hooks": ("HK_SKIP_HOOKS=pre-commit,pre-push git commit -m x", DENY),
    "husky-zero": ("HUSKY=0 git push", DENY),
    "lefthook-zero": ("LEFTHOOK=0 git commit -m x", DENY),
    "git-config-parameters": (
        "GIT_CONFIG_PARAMETERS=\"'core.hooksPath'='/dev/null'\" git push",
        DENY,
    ),
    "git-config-key-env": (
        "GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=core.hooksPath GIT_CONFIG_VALUE_0=/dev/null git push",
        DENY,
    ),
    # persistent config disables
    "config-hookspath-set": ("git config core.hooksPath /dev/null", DENY),
    "config-hookspath-local": ("git config --local core.hooksPath .nohooks", DENY),
    "config-hk-skiphook": ("git config --local hk.skipHook pre-push", DENY),
    "config-hk-hook-disabled": (
        "git config --local hook.hk-pre-push.enabled false",
        DENY,
    ),
    "dash-c-hk-skiphook": ("git -c hk.skipHook=pre-push push", DENY),
    # nesting
    "bash-c-no-verify": ("bash -c 'git push --no-verify origin main'", DENY),
    "sh-c-hk-zero": ("sh -c 'HK=0 git push'", DENY),
    # helpers that push to main with hooks off
    "push-origin-main-helper": ("push-origin-main", DENY),
    # worktrunk: --no-hooks (and deprecated --no-verify) skip wt's pre-merge gate
    "wt-merge-no-hooks": ("wt merge --no-hooks", DENY),
    "wt-merge-no-verify": ("wt merge main --no-verify", DENY),
    "wt-step-commit-no-hooks": ("wt step commit --no-hooks", DENY),
    "wt-merge-allowed": ("wt merge", SILENT),
    # allowed neighbours
    "hk-profile-allowed": ("HK_PROFILE=slow hk check --all", SILENT),
    "hk-one-allowed": ("HK=1 git commit -m x", SILENT),
    "config-get-hookspath": ("git config --get core.hooksPath", SILENT),
    "echo-mentions-hk": ('echo "never use HK=0 or --no-verify"', SILENT),
    "push-dry-run-n": ("git push -n origin main", SILENT),
    "plain-push": ("git push origin feat/x", SILENT),
    "bash-c-plain": ("bash -c 'git status'", SILENT),
}


@pytest.mark.parametrize("name", BASH_CASES)
def test_hook_skip_bash(hooks: HookRunner, name: str) -> None:
    command, expected = BASH_CASES[name]
    run = hooks.run_payload(PY_HOOK, _bash(command))
    assert run.exit_code == 0 and run.stderr == "" and not run.failed_open, run.log
    assert run.decision == expected, f"{command!r} -> {run.stdout}"


WRITE_CASES: dict[str, tuple[str, str, str]] = {
    # PR zq#102: "Pushed via /tmp script with --no-verify"
    "tmp-script-push-no-verify": (
        "/tmp/push.sh",
        "#!/bin/sh\nset -e\ngit push --no-verify origin feat/x\n",
        DENY,
    ),
    "script-hk-zero": ("/tmp/land.sh", "#!/usr/bin/env bash\nHK=0 git push\n", DENY),
    "python-no-verify": (
        "/tmp/p.py",
        'import subprocess\nsubprocess.run(["git", "push", "--no-verify"])\n',
        DENY,
    ),
    "markdown-prose-allowed": (
        "/tmp/notes.md",
        "Never run `git push --no-verify`; HK=0 skips hooks.\n",
        SILENT,
    ),
    "script-plain-push-allowed": (
        "/tmp/ok.sh",
        "#!/bin/sh\ngit push origin feat/x\n",
        SILENT,
    ),
}


@pytest.mark.parametrize("name", WRITE_CASES)
def test_hook_skip_write(hooks: HookRunner, name: str) -> None:
    path, content, expected = WRITE_CASES[name]
    run = hooks.run_payload(PY_HOOK, _write(path, content))
    assert run.exit_code == 0 and run.stderr == "" and not run.failed_open, run.log
    assert run.decision == expected, f"{path} -> {run.stdout}"


def _hooks_toml() -> dict[str, Any]:
    path = os.environ.get("ZYS1758_HOOKS_TOML")
    if not path:
        pytest.skip("ZYS1758_HOOKS_TOML not set (run via zys-1758/run-tests.sh)")
    return tomllib.loads(Path(path).read_text())


def test_tripwire_rows_have_a_command() -> None:
    """A policy-only row is skipped by agent-hooks dispatch, so the guard never ran."""
    rows = [r for r in _hooks_toml()["hooks"] if "gate-bypass-tripwire" in r["name"]]
    assert len(rows) == 2
    for row in rows:
        assert row.get("command"), f"{row['name']} has no command: dispatch skips it"
        assert "gate-bypass-tripwire.py" in row["command"][0]
        assert row.get("on_failure") == "block"


def test_tripwire_bash_row_matches_run_command_aliases() -> None:
    row = next(
        r
        for r in _hooks_toml()["hooks"]
        if r["name"] == "pretooluse-gate-bypass-tripwire"
    )
    for alias in ("Bash", "agentmux_capability_run_command", "run_terminal_command"):
        assert alias in row["matcher"].split("|"), alias


# --- omp: run_command arrives as `write xd://…run_command` or inside `eval` ----
# The omp bridge passes the raw tool name. The ZYS-1758 push was
#   write {path: "xd://mcp__capability_agentmux_capability_run_command",
#          content: "{\"command\":\"cd … && git push --no-verify origin main …\"}"}
# and the f4bd6e86 commit was the same shape with `HK=0 git commit`.

import json as _json


def _omp_run_command(
    command: str, server: str = "mcp__capability_agentmux_capability_run_command"
) -> dict[str, Any]:
    content = _json.dumps({"command": command, "purpose": "x", "timeout_seconds": 180})
    return {
        "tool_name": "write",
        "toolName": "write",
        "tool_input": {
            "path": f"xd://{server}",
            "i": "Pushing main",
            "content": content,
        },
    }


def _omp_eval(command: str) -> dict[str, Any]:
    call = _json.dumps({"command": command, "timeout_seconds": 120})
    code = f"r=await tool.mcp__capability_agentmux_capability_run_command({call})\nprint(r)"
    return {
        "tool_name": "eval",
        "toolName": "eval",
        "tool_input": {"language": "py", "code": code},
    }


OMP_CASES: dict[str, tuple[dict[str, Any], str]] = {
    "omp-shallowpelican-push": (
        _omp_run_command(
            "cd /Users/x/.worktrees/capability-replicas-zys-1731 && git push --no-verify origin main 2>&1 | tail -4 && git rev-parse origin/main"
        ),
        DENY,
    ),
    "omp-always-on-hk0-commit": (
        _omp_run_command(
            "cd /Users/x/capability-replicas && HK=0 git commit -m \"$(cat <<'EOF'\nfix: x\nEOF\n)\" -- a.ts",
            server="mcp__capability_always_on_agentmux_capability_run_command",
        ),
        DENY,
    ),
    "omp-eval-run-command-no-verify": (
        _omp_eval("git commit --no-verify -m wip"),
        DENY,
    ),
    "omp-meta-exec-run-command": (
        {
            "tool_name": "write",
            "tool_input": {
                "path": "xd://mcp__capability_meta_capability_exec",
                "content": _json.dumps(
                    {
                        "name": "run_command",
                        "input": {"command": "HK=0 git push origin main"},
                    }
                ),
            },
        },
        DENY,
    ),
    "omp-meta-exec-plain": (
        {
            "tool_name": "write",
            "tool_input": {
                "path": "xd://mcp__capability_meta_capability_exec",
                "content": _json.dumps(
                    {"name": "run_command", "input": {"command": "sleep 25"}}
                ),
            },
        },
        SILENT,
    ),
    "omp-plain-push": (
        _omp_run_command("cd /tmp/w && git push -u origin zys-1731 2>&1 | tail -8"),
        SILENT,
    ),
    "omp-eval-plain": (_omp_eval("git log --oneline -6"), SILENT),
}


@pytest.mark.parametrize("name", sorted(OMP_CASES))
def test_omp_run_command_shapes(hooks: HookRunner, name: str) -> None:
    payload, want = OMP_CASES[name]
    run = hooks.run_payload(PY_HOOK, payload)
    assert run.exit_code == 0 and not run.failed_open, run.log
    assert run.decision == want, f"{name} -> {run.stdout}"


def test_tripwire_rows_match_omp_raw_tool_names() -> None:
    """The omp bridge sends the raw names `write` and `eval`, not Bash."""
    rows = {
        r["name"]: r
        for r in _hooks_toml()["hooks"]
        if "gate-bypass-tripwire" in r["name"]
    }
    names = set(rows["pretooluse-gate-bypass-tripwire"]["matcher"].split("|")) | set(
        rows["pretooluse-gate-bypass-tripwire-write"]["matcher"].split("|")
    )
    assert {"write", "eval"} <= names
