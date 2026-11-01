"""eval-sleep-guard.py: multi-second sleeps (>= 5s / 5000ms) inside eval are denied (ZYS-1917)."""

from __future__ import annotations

import pytest
from hook_harness import HookRunner

HOOK = "eval-sleep-guard.py"
EXPECTED_DENY_REASON = (
    "Multi-second sleep inside eval (>= 5s / 5000ms) is not allowed for polling or waiting. "
    "Call agentmux_capability_wait (or arm a capability wait) instead."
)


def _eval_payload(code: str, tool_name: str = "eval") -> dict:
    return {
        "hook_event_name": "PreToolUse",
        "tool_name": tool_name,
        "tool_input": {"code": code},
    }


DENIED_CODES = {
    "js-settimeout-5000": "await new Promise(r => setTimeout(r, 5000))",
    "js-settimeout-120000": "await new Promise((resolve) => setTimeout(resolve, 120000))",
    "js-bun-sleep-6000": "await Bun.sleep(6000)",
    "py-time-sleep-5": "import time; time.sleep(5)",
    "py-asyncio-sleep-10": "await asyncio.sleep(10)",
    "js-settimeout-arrow-body-5000": "setTimeout(() => { console.log(1, 2); }, 5000)",
}

ALLOWED_CODES = {
    "js-settimeout-100": "await new Promise(r => setTimeout(r, 100))",
    "js-bun-sleep-500": "await Bun.sleep(500)",
    "py-time-sleep-0.5": "import time; time.sleep(0.5)",
    "py-asyncio-sleep-1": "await asyncio.sleep(1)",
    "no-sleep": "print(1 + 1)",
}


@pytest.mark.parametrize("name", DENIED_CODES)
@pytest.mark.parametrize("tool_name", ("eval", "mcp__eval"))
def test_denies_multi_second_sleep(hooks: HookRunner, name: str, tool_name: str) -> None:
    run = hooks.run_payload(HOOK, _eval_payload(DENIED_CODES[name], tool_name=tool_name))
    assert run.exit_code == 0
    assert run.stderr == ""
    assert not run.failed_open
    assert run.decision == "deny"
    reason = (run.output or {})["hookSpecificOutput"]["permissionDecisionReason"]
    assert reason == EXPECTED_DENY_REASON


@pytest.mark.parametrize("name", ALLOWED_CODES)
def test_allows_short_or_non_sleep_eval(hooks: HookRunner, name: str) -> None:
    run = hooks.run_payload(HOOK, _eval_payload(ALLOWED_CODES[name]))
    assert run.exit_code == 0
    assert run.stderr == ""
    assert not run.failed_open
    assert run.decision == "none"
    assert run.stdout == ""


def test_ignores_unrelated_tools(hooks: HookRunner) -> None:
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Write",
        "tool_input": {"code": "time.sleep(10)"},
    }
    run = hooks.run_payload(HOOK, payload)
    assert run.exit_code == 0
    assert run.decision == "none"
    assert run.stdout == ""
