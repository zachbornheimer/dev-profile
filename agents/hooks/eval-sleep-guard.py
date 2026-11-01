#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""PreToolUse (eval|mcp__eval) — deny multi-second sleeps inside eval cells (ZYS-1917).

Polling or waiting inside an eval cell via ``time.sleep(>= 5)``,
``asyncio.sleep(>= 5)``, ``setTimeout(..., >= 5000)``, or ``Bun.sleep(>= 5000)``
holds the eval kernel open instead of yielding to the capability wait primitive.
Short delays (< 5 s / < 5000 ms, such as UI debounce checks) are allowed.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))

from hook_common import Decision, HookEvent, run_hook

HOOK_NAME = "eval-sleep-guard"

EVAL_TOOL_NAMES = frozenset(
    {
        "eval",
        "mcp__eval",
        "mcp__capability__eval",
        "mcp__capability_eval",
    }
)

MIN_SLEEP_SECONDS = 5.0
MIN_SLEEP_MS = 5000.0

DENY_REASON = (
    "Multi-second sleep inside eval (>= 5s / 5000ms) is not allowed for polling or waiting. "
    "Call agentmux_capability_wait (or arm a capability wait) instead."
)

_PY_SLEEP_CALL_RE = re.compile(r"\b(?:time|asyncio)\.sleep\s*\(")
_BUN_SLEEP_CALL_RE = re.compile(r"\bBun\.sleep(?:Sync)?\s*\(")
_SET_TIMEOUT_CALL_RE = re.compile(r"\bsetTimeout\s*\(")


def _eval_numeric_node(node: ast.AST) -> float | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        if isinstance(node.value, bool):
            return None
        return float(node.value)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        operand = _eval_numeric_node(node.operand)
        if operand is None:
            return None
        return operand if isinstance(node.op, ast.UAdd) else -operand
    if isinstance(node, ast.BinOp) and isinstance(
        node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div)
    ):
        left = _eval_numeric_node(node.left)
        right = _eval_numeric_node(node.right)
        if left is None or right is None:
            return None
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        return left / right if right != 0 else None
    return None


def _parse_number(expr: str) -> float | None:
    cleaned = expr.strip()
    if "=" in cleaned:
        key, _, rhs = cleaned.partition("=")
        if key.strip().isidentifier():
            cleaned = rhs.strip()
    if not cleaned:
        return None
    try:
        tree = ast.parse(cleaned, mode="eval")
    except (SyntaxError, ValueError):
        return None
    return _eval_numeric_node(tree.body)


def _extract_call_args(code: str, start_after_open_paren: int) -> list[str]:
    args: list[str] = []
    current: list[str] = []
    depth = 1
    index = start_after_open_paren
    quote: str | None = None
    while index < len(code) and depth > 0:
        ch = code[index]
        if quote is not None:
            current.append(ch)
            if ch == "\\" and index + 1 < len(code):
                index += 1
                current.append(code[index])
            elif ch == quote:
                quote = None
            index += 1
            continue
        if ch in ("'", '"', "`"):
            quote = ch
            current.append(ch)
        elif ch in ("(", "[", "{"):
            depth += 1
            current.append(ch)
        elif ch in (")", "]", "}"):
            depth -= 1
            if depth == 0:
                args.append("".join(current).strip())
                break
            current.append(ch)
        elif ch == "," and depth == 1:
            args.append("".join(current).strip())
            current = []
        else:
            current.append(ch)
        index += 1
    return args


def has_multi_second_sleep(code: str) -> bool:
    for match in _PY_SLEEP_CALL_RE.finditer(code):
        args = _extract_call_args(code, match.end())
        if args:
            seconds = _parse_number(args[0])
            if seconds is not None and seconds >= MIN_SLEEP_SECONDS:
                return True
    for match in _BUN_SLEEP_CALL_RE.finditer(code):
        args = _extract_call_args(code, match.end())
        if args:
            milliseconds = _parse_number(args[0])
            if milliseconds is not None and milliseconds >= MIN_SLEEP_MS:
                return True
    for match in _SET_TIMEOUT_CALL_RE.finditer(code):
        args = _extract_call_args(code, match.end())
        if len(args) >= 2:
            milliseconds = _parse_number(args[1])
            if milliseconds is not None and milliseconds >= MIN_SLEEP_MS:
                return True
    return False


def decide(event: HookEvent) -> Decision | None:
    if event.raw_tool_name not in EVAL_TOOL_NAMES:
        return None
    code = event.tool_input("code")
    if not code or not has_multi_second_sleep(code):
        return None
    return Decision.deny(DENY_REASON, log_detail="eval-sleep")


if __name__ == "__main__":
    run_hook(HOOK_NAME, decide)
