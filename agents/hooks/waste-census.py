#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Count waste classes in one agent transcript, deterministically.

A learning loop that reads only tool failures sees one class of waste and
proposes one fix. That is what happened to the transcript this script was
written against: four denied Bash calls drew twelve hypotheses, all naming the
same mechanism, while three identical escalations and six fetches of the wrong
tool's documentation — carrying most of the wall time — were invisible because
neither is an error.

Both are waste. This prints every class with its item ids so a diagnosis can
say which items it explains and which it does not.

    waste-census.py <transcript.json|jsonl> [--json]

Accepts the exported item shape, omp session JSONL and Claude Code project JSONL. For the
last two an item id is the raw 1-based line number of the transcript file.

Classes:

    tool_error         a system item reporting an error or an unavailable tool
    repeat_denied_tool the same denied tool called again after denial
    duplicate_call     the same tool with the same arguments, again
    repeat_text        the same agent message sent again (escalation loop)
    refetch            the same URL fetched more than once
    user_recovery      the user supplying the diagnosis the agent did not reach

Exit 0 whenever the transcript parses. It reports; it does not judge.
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

RECOVERY_PHRASES = re.compile(
    r"why (aren't|are you not|didn't) you"
    r"|do you have"
    r"|what'?s causing you"
    r"|why (did|do) you stop"
    r"|you should (use|always)"
    r"|not complet"
    r"|how many times|answer my question|i (already |just )?told you",
    re.IGNORECASE,
)
# Waiting on a job or subagent with the same arguments is polling, not a repeated request.
POLLING_TOOLS = frozenset({"wait"})
REPEAT_MIN_CHARS = 60
URL_FETCH_TOOLS = frozenset({"WebFetch", "web_fetch", "fetch"})


def omp_items(lines: list[str]) -> list[dict[str, Any]]:
    """omp session JSONL as census items; ``id`` is the raw 1-based line number.

    Only ``message`` entries carry conversation. The ``developer`` role and the
    ``custom*`` bookkeeping entries are harness text, not user or agent turns.
    """
    items: list[dict[str, Any]] = []
    for number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        entry = json.loads(line)
        message = entry.get("message") if isinstance(entry, dict) else None
        if not isinstance(message, dict):
            continue
        parts = message.get("content")
        parts = parts if isinstance(parts, list) else []
        text = "\n".join(p["text"] for p in parts if p.get("type") == "text" and p.get("text"))
        role = message.get("role")
        if role == "user":
            items.append({"id": number, "source": "user", "text": text})
        elif role == "assistant":
            calls = [
                {"name": p.get("name", "?"), "arguments": p.get("arguments")}
                for p in parts
                if p.get("type") == "toolCall"
            ]
            items.append({"id": number, "source": "agent", "text": text, "tool_calls": calls})
        elif role == "toolResult":
            items.append(
                {
                    "id": number,
                    "source": "system",
                    "text": text,
                    "tool_name": message.get("toolName"),
                    "is_error": bool(message.get("isError"))
                    and not text.startswith("Skipped due to queued user message"),
                }
            )
    return items


MACHINE_USER_TEXT = re.compile(
    r"\s*(<[a-z][\w-]*[\s>]|\[Request interrupted|This session is being continued)", re.IGNORECASE
)


def _block_text(content: Any) -> str:
    """Text of a message ``content`` that is a string or a list of typed blocks."""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    return "\n".join(
        block["text"]
        for block in content
        if isinstance(block, dict) and block.get("type") == "text" and block.get("text")
    )


def claude_items(lines: list[str]) -> list[dict[str, Any]]:
    """Claude Code project JSONL as census items; ``id`` is the raw 1-based line number.

    Tool results arrive as ``tool_result`` blocks inside ``user`` entries and name no tool, so
    the name is carried over from the ``tool_use`` that has the same id. Sidechain (subagent)
    entries, ``isMeta`` text and harness-injected user text are not the conversation.
    """
    items: list[dict[str, Any]] = []
    tool_names: dict[str, str] = {}
    for number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        entry = json.loads(line)
        message = entry.get("message") if isinstance(entry, dict) else None
        kind = entry.get("type") if isinstance(entry, dict) else None
        if kind not in ("user", "assistant") or not isinstance(message, dict):
            continue
        if entry.get("isSidechain") or entry.get("isMeta"):
            continue
        content = message.get("content")
        blocks = [b for b in content if isinstance(b, dict)] if isinstance(content, list) else []
        if kind == "assistant":
            calls = [b for b in blocks if b.get("type") == "tool_use"]
            for block in calls:
                tool_names[block.get("id", "")] = block.get("name", "?")
            items.append(
                {
                    "id": number,
                    "source": "agent",
                    "text": _block_text(content),
                    "tool_calls": [
                        {"name": b.get("name", "?"), "arguments": b.get("input")} for b in calls
                    ],
                }
            )
            continue
        for block in blocks:
            if block.get("type") == "tool_result":
                items.append(
                    {
                        "id": number,
                        "source": "system",
                        "text": _block_text(block.get("content")),
                        "tool_name": tool_names.get(block.get("tool_use_id", ""), "?"),
                        "is_error": bool(block.get("is_error")),
                    }
                )
        text = _block_text(content)
        if text.strip() and not MACHINE_USER_TEXT.match(text):
            items.append({"id": number, "source": "user", "text": text})
    return items


def _resolve_tool_names(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Carry each tool call's name onto its matching tool-result item.

    ``annotated.json`` exports list ``tool_calls`` (with ``id`` and ``name``) on
    the agent item and only ``tool_call_id`` on the system result item, so
    without this join every ``tool_error`` in a ``turns`` export renders as
    ``(?)``.
    """
    tool_names: dict[str, str] = {}
    for item in items:
        for tc in item.get("tool_calls") or []:
            if not isinstance(tc, dict):
                continue
            call_id = tc.get("id") or tc.get("toolCallId") or tc.get("tool_call_id")
            name = tc.get("name") or tc.get("tool_name") or tc.get("toolName")
            if call_id and name:
                tool_names[str(call_id)] = str(name)
    resolved: list[dict[str, Any]] = []
    for item in items:
        call_id = item.get("tool_call_id") or item.get("toolCallId")
        if call_id and item.get("tool_name") in (None, "", "?"):
            item = {**item, "tool_name": tool_names.get(str(call_id), "?")}
        resolved.append(item)
    return resolved


def load(path: Path) -> list[dict[str, Any]]:
    """Every item in the transcript, whichever export shape it arrived in."""
    raw = path.read_text()
    if path.suffix != ".jsonl":
        document = json.loads(raw)
        if isinstance(document, list):
            return _resolve_tool_names(document)
        turns = document.get("turns") or []
        items: list[dict[str, Any]] = []
        for turn in turns:
            for side in ("user", "response"):
                value = turn.get(side)
                if isinstance(value, str):
                    value = json.loads(value) if value.strip().startswith(("[", "{")) else []
                # User items in this export carry only id/text/timestamp — no
                # `source`. Without the side tag they fall through to the agent
                # branch and every user recovery prompt is reported as zero.
                items.extend({**item, "_side": side} for item in value or [])
        return _resolve_tool_names(items)
    lines = raw.splitlines()
    head = [json.loads(line) for line in lines[:50] if line.strip()]
    if any(entry.get("type") == "session" for entry in head[:3]):
        return omp_items(lines)
    if any(entry.get("type") in ("user", "assistant") and "message" in entry for entry in head):
        return claude_items(lines)
    return [json.loads(line) for line in lines if line.strip()]


def side_of(item: dict[str, Any]) -> str:
    """``user``, ``agent`` or ``system`` — the side that produced the item.

    An explicit ``source`` wins: tool results travel inside the ``response``
    list yet are system-authored, and reading them as agent text turned every
    denied call into a "repeat_text" finding.
    """
    explicit = item.get("source")
    if explicit:
        return explicit
    if item.get("tool_call_id") or item.get("toolCallId"):
        return "system"
    if "_side" in item:
        return "user" if item["_side"] == "user" else "agent"
    return "agent"


def text_of(item: dict[str, Any]) -> str:
    return (item.get("text") or item.get("content") or "").strip()


def calls_of(item: dict[str, Any]) -> list[tuple[str, str]]:
    """(tool name, stable argument key) for each call on an agent item."""
    return [
        (call.get("name", "?"), json.dumps(call.get("arguments") or {}, sort_keys=True))
        for call in item.get("tool_calls") or []
    ]


def url_of(arguments: str) -> str:
    try:
        parsed = json.loads(arguments)
    except ValueError:
        return ""
    return parsed.get("url") or parsed.get("prompt") or ""


def _target_of(arguments: str) -> str:
    """The path an omp device call addresses (``xd://tool``), else empty."""
    try:
        parsed = json.loads(arguments)
    except ValueError:
        return ""
    return parsed.get("path", "") if isinstance(parsed, dict) else ""


def census(items: list[dict[str, Any]]) -> dict[str, list[str]]:
    findings: dict[str, list[str]] = defaultdict(list)

    seen_calls: Counter[tuple[str, str]] = Counter()
    seen_text: Counter[str] = Counter()
    seen_urls: Counter[str] = Counter()
    denied_tools: set[str] = set()

    for item in items:
        item_id = item.get("id")
        ref = f"item:{item_id}"
        side = side_of(item)

        if side == "system":
            body = text_of(item)
            # A structured transcript says whether the call failed; scanning output text for
            # "error" would also count the stdout of a command that succeeded.
            failed = (
                item["is_error"]
                if "is_error" in item
                else "<tool_use_error>" in body or body.lower().startswith("error")
            )
            if failed:
                findings["tool_error"].append(f"{ref} ({item.get('tool_name') or '?'})")
                # Track denied tools. omp names the missing device ("No such tool: xd://x") and
                # serves every device through one shared tool (`write`), so key on the device.
                tool_name = item.get("tool_name") or ""
                missing = re.search(r"no such tool:\s*(\S+?)\.?(?:\s|$)", body, re.IGNORECASE)
                if missing:
                    denied_tools.add(missing.group(1))
                elif "no such tool" in body.lower() or "not available" in body.lower():
                    denied_tools.add(tool_name)
            continue

        if side == "user":
            if RECOVERY_PHRASES.search(text_of(item)):
                findings["user_recovery"].append(ref)
            continue

        for name, arguments in calls_of(item):
            # Check if calling a tool that was previously denied
            if name in denied_tools or _target_of(arguments) in denied_tools:
                findings["repeat_denied_tool"].append(f"{ref} ({name})")

            key = (name, arguments)
            seen_calls[key] += 1
            if seen_calls[key] == 2 and name not in POLLING_TOOLS:
                findings["duplicate_call"].append(f"{ref} ({name})")
            if name in URL_FETCH_TOOLS:
                url = url_of(arguments)
                if url:
                    seen_urls[url] += 1
                    if seen_urls[url] == 2:
                        findings["refetch"].append(f"{ref} ({url})")

        body = text_of(item)
        if len(body) >= REPEAT_MIN_CHARS:
            seen_text[body] += 1
            if seen_text[body] == 2:
                findings["repeat_text"].append(f"{ref} ({body[:60]!r})")

    return dict(findings)


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__.strip().splitlines()[8], file=sys.stderr)
        return 2

    path = Path(argv[1]).expanduser()
    as_json = "--json" in argv[2:]
    try:
        items = load(path)
    except (OSError, ValueError) as error:
        print(f"{path}: {error}", file=sys.stderr)
        return 2

    findings = census(items)
    total = sum(len(refs) for refs in findings.values())

    if as_json:
        print(json.dumps({"items": len(items), "waste": findings}, indent=2))
        return 0

    print(f"{path.name}: {len(items)} items, {total} waste events\n")
    for name in (
        "tool_error",
        "repeat_denied_tool",
        "duplicate_call",
        "repeat_text",
        "refetch",
        "user_recovery",
    ):
        refs = findings.get(name, [])
        print(f"{name:15} {len(refs):3}")
        for ref in refs:
            print(f"                {ref}")
    print(
        "\nA diagnosis that explains only tool_error has not explained this run:"
        "\nname the classes it leaves out before proposing a fix."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
