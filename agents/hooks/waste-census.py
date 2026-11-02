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
    waste-census.py --fleet [--provider NAME] [--model SUBSTR] [--since ISO] [--until ISO]
                         [--sessions-dir DIR] [--exclude SUBSTR] [--json]

Accepts the exported item shape, omp session JSONL and Claude Code project JSONL. For the
last two an item id is the raw 1-based line number of the transcript file. Fleet
mode streams every session transcript under --sessions-dir (default
~/.omp/agent/sessions, one and two levels deep) and attributes burn per
provider/model through a date window: calls, cost, cache-read, intent
categories, duplicate calls, first-call-after-switch cost, top sessions,
intents and hours.

Classes:

    eviction           a harness receipt replacing an evicted tool result
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

# omp replaces an evicted tool result with a receipt such as
# ``[shaken ~131 tokens — recover: artifact://82 (region 4)]``. The call itself
# succeeded and the content lives on in the artifact store, so this is context
# loss, not a tool failure: on omp_01a18dd0, 37 of 43 "tool errors" were these
# receipts, overstating failure 7x and hiding that the agent worked from
# amputated context.
SHAKEN_RECEIPT = re.compile(r"\[shaken ~(\d+) tokens")

RECOVERY_PHRASES = re.compile(
    r"why (aren't|are you not|didn't) you"
    r"|do you have"
    r"|what'?s causing you"
    r"|why (did|do) you stop"
    r"|you should (use|always)"
    r"|not complet"
    r"|how many times|answer my question|i (already |just )?told you"
    # Forms a real session took that none of the above matched (omp_01a18dd0,
    # T15-T17): the user supplying the correction the agent did not reach.
    r"|how many (tokens|dollars|turns)"
    r"|that'?s not a valid"
    r"|(was|were) (that|those|the|this|these).{0,40}synthetic"
    r"|(give|show) me the (actual|real)"
    r"|i'?m really confused|i'?m confused"
    r"|you decided to not do what i'?ve asked"
    # omp_01a18960 items 17/18/21: an 8.75h-dead turn revived by "please
    # continue", the identity question after a silent machine move, and the
    # user reporting the move themselves. The gemini-filter-resume extension
    # sends the same "please continue" — a turn that needed continuation is a
    # recovery either way.
    r"|please continue"
    r"|which machine (are you|am i)"
    r"|i'?(?:ve| have) switched you",
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
        text = "\n".join(
            p["text"] for p in parts if p.get("type") == "text" and p.get("text")
        )
        role = message.get("role")
        if role == "user":
            items.append({"id": number, "source": "user", "text": text})
        elif role == "assistant":
            calls = [
                {"name": p.get("name", "?"), "arguments": p.get("arguments")}
                for p in parts
                if p.get("type") == "toolCall"
            ]
            items.append(
                {"id": number, "source": "agent", "text": text, "tool_calls": calls}
            )
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
    r"\s*(<[a-z][\w-]*[\s>]|\[Request interrupted|This session is being continued)",
    re.IGNORECASE,
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
        blocks = (
            [b for b in content if isinstance(b, dict)]
            if isinstance(content, list)
            else []
        )
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
                        {"name": b.get("name", "?"), "arguments": b.get("input")}
                        for b in calls
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
                    value = (
                        json.loads(value)
                        if value.strip().startswith(("[", "{"))
                        else []
                    )
                # User items in this export carry only id/text/timestamp — no
                # `source`. Without the side tag they fall through to the agent
                # branch and every user recovery prompt is reported as zero.
                items.extend({**item, "_side": side} for item in value or [])
        return _resolve_tool_names(items)
    lines = raw.splitlines()
    head = [json.loads(line) for line in lines[:50] if line.strip()]
    if any(entry.get("type") == "session" for entry in head[:3]):
        return omp_items(lines)
    if any(
        entry.get("type") in ("user", "assistant") and "message" in entry
        for entry in head
    ):
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


def census(items: list[dict[str, Any]]) -> tuple[dict[str, list[str]], int]:
    findings: dict[str, list[str]] = defaultdict(list)
    # Total tokens the harness reported shaken out of context: a census that
    # counts 193 evictions but not the ~N tokens behind them cannot say
    # whether retention below N would change behavior or only cost.
    evicted_tokens = 0

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
            # An eviction receipt is context loss, not a tool failure: count it
            # as its own class so a diagnosis can say which one it is looking at.
            receipt = SHAKEN_RECEIPT.search(body)
            if receipt:
                findings["eviction"].append(ref)
                evicted_tokens += int(receipt.group(1))
                continue
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
                missing = re.search(
                    r"no such tool:\s*(\S+?)\.?(?:\s|$)", body, re.IGNORECASE
                )
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
    return dict(findings), evicted_tokens


#
# Fleet mode: per-provider (and optionally per-model) burn attribution across
# every omp session transcript in a window. Answers the quota question the
# per-transcript census cannot: which behaviors burned a provider's window, at
# what call volume and context cost, between two dates. Category regexes and
# the duplicate grouping are fixed so two runs over the same window agree.
#

ORCH_INTENT = re.compile(
    r"todo|task|spawn|plan|decision|pin|resolve|steer|agent|skill"
    r"|tool_search|tool_call|assign|claim|review|atask",
    re.IGNORECASE,
)
POLL_INTENT = re.compile(
    r"wait|poll|status|checks?\b|ci\b|gh run|sleep|watch|log|tail"
    r"|monitor|progress|pr |merge|push",
    re.IGNORECASE,
)
IMPL_INTENT = re.compile(
    r"write|edit|implement|fix|add|update|create|patch|commit|deploy"
    r"|rebase|apply|port|cutover|bun",
    re.IGNORECASE,
)

_RAW_ROLE = re.compile(r'"role":"([^"]*)"')
_RAW_TYPE = re.compile(r'"type":"([^"]*)"')
_RAW_MODEL = re.compile(r'"model":"([^"]*)"')
_RAW_TS = re.compile(r'"timestamp":"(\d{4}-\d{2}-\d{2}[^"]*)"')


def _intent_category(tools: list[tuple[str, str]]) -> str:
    """One of text-only / orchestrate / poll-wait / implement / other."""
    if not tools:
        return "text-only"
    joined = " ".join(f"{name}:{intent}" for name, intent in tools)
    if ORCH_INTENT.search(joined):
        return "orchestrate/review"
    if POLL_INTENT.search(joined):
        return "poll/wait/push"
    if IMPL_INTENT.search(joined):
        return "implement"
    return "other"


def fleet_census(
    sessions_dir: Path,
    provider: str = "",
    model: str = "",
    since: str = "",
    until: str = "",
    exclude: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Burn attribution for assistant calls matching the filters, per window.

    ``model`` is a substring match (``grok`` matches ``grok-4.7``); so is
    ``provider``. ``since``/``until`` compare against the record timestamp as
    ISO strings. Files are streamed line by line; only matching assistant
    lines are JSON-parsed.
    """
    if until and len(until) == 10:
        until = until + "T23:59"

    paths: list[Path] = []
    for pattern in ("*/*.jsonl", "*/*/*.jsonl"):
        paths.extend(sessions_dir.glob(pattern))
    paths = sorted({p for p in paths if not any(x in str(p) for x in exclude)})

    cat_calls: Counter[str] = Counter()
    cat_cost: Counter[str] = Counter()
    dup_groups: Counter[tuple[str, str]] = Counter()
    dup_cost: Counter[tuple[str, str]] = Counter()
    intent_calls: Counter[str] = Counter()
    intent_cost: Counter[str] = Counter()
    session_cost: Counter[str] = Counter()
    session_calls: Counter[str] = Counter()
    hourly: dict[str, dict[str, float]] = defaultdict(
        lambda: {"calls": 0, "cost": 0.0, "cache_read": 0.0}
    )
    totals = {
        "calls": 0,
        "cost": 0.0,
        "cache_read": 0,
        "input": 0,
        "output": 0,
        "stop_error": 0,
        "first_after_switch_calls": 0,
        "first_after_switch_cost": 0.0,
        "first_after_switch_input": 0,
    }

    scanned = 0
    for path in paths:
        scanned += 1
        prev_model: str | None = None
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for raw in handle:
                if '"role":"' not in raw and '"model_change"' not in raw:
                    continue
                kind = _RAW_TYPE.search(raw)
                if kind and kind.group(1) == "model_change":
                    continue
                role = _RAW_ROLE.search(raw)
                if not role or role.group(1) != "assistant":
                    continue
                found = _RAW_MODEL.search(raw)
                if not found:
                    continue
                entry_model = found.group(1)
                if model and model not in entry_model:
                    prev_model = entry_model
                    continue
                stamp = _RAW_TS.search(raw)
                timestamp = stamp.group(1) if stamp else ""
                if since and timestamp < since:
                    prev_model = entry_model
                    continue
                if until and timestamp > until:
                    prev_model = entry_model
                    continue

                entry = json.loads(raw)
                message = entry.get("message") or {}
                if provider and provider not in (message.get("provider") or ""):
                    prev_model = entry_model
                    continue

                usage = message.get("usage") or {}
                cost = ((usage.get("cost") or {}).get("total")) or 0.0
                cache_read = usage.get("cacheRead") or 0
                tools = [
                    (part.get("name", "?"), part.get("intent") or "")
                    for part in message.get("content") or []
                    if part.get("type") == "toolCall"
                ]
                category = _intent_category(tools)
                canon = " ".join(sorted({name for name, _ in tools})) or "text"
                joined = " | ".join(f"{name}:{intent}" for name, intent in tools)[:120]
                group = (canon, joined[:60])

                totals["calls"] += 1
                totals["cost"] += cost
                totals["cache_read"] += cache_read
                totals["input"] += usage.get("input") or 0
                totals["output"] += usage.get("output") or 0
                if message.get("stopReason") == "error":
                    totals["stop_error"] += 1
                if prev_model is not None and prev_model != entry_model:
                    totals["first_after_switch_calls"] += 1
                    totals["first_after_switch_cost"] += cost
                    totals["first_after_switch_input"] += usage.get("input") or 0
                prev_model = entry_model

                cat_calls[category] += 1
                cat_cost[category] += cost
                dup_groups[group] += 1
                dup_cost[group] += cost
                for _, intent in tools:
                    key = intent[:70]
                    intent_calls[key] += 1
                    intent_cost[key] += cost
                session_cost[path.name] += cost
                session_calls[path.name] += 1
                bucket = hourly[timestamp[:13]]
                bucket["calls"] += 1
                bucket["cost"] += cost
                bucket["cache_read"] += cache_read

    duplicate_extra = sum(n - 1 for n in dup_groups.values() if n > 1)
    duplicate_cost = sum(
        dup_cost[g] * (n - 1) / n for g, n in dup_groups.items() if n > 1
    )
    return {
        "files_scanned": scanned,
        "totals": totals,
        "categories": {
            name: {"calls": cat_calls[name], "cost": round(cat_cost[name], 2)}
            for name in sorted(cat_cost, key=lambda k: -cat_cost[k])
        },
        "duplicates": {
            "extra_calls": duplicate_extra,
            "est_cost": round(duplicate_cost, 2),
            "top_groups": [
                {
                    "repeat": n,
                    "cost": round(dup_cost[g], 2),
                    "tools": g[0],
                    "intent": g[1],
                }
                for g, n in dup_groups.most_common(10)
                if n > 1
            ],
        },
        "top_intents": [
            {"intent": i, "calls": intent_calls[i], "cost": round(intent_cost[i], 2)}
            for i in sorted(intent_cost, key=lambda k: -intent_cost[k])[:15]
        ],
        "top_sessions": [
            {"file": s, "calls": session_calls[s], "cost": round(session_cost[s], 2)}
            for s in sorted(session_cost, key=lambda k: -session_cost[k])[:12]
        ],
        "hourly_top": [
            {
                "hour": h,
                **{k: round(v, 2) if k == "cost" else int(v) for k, v in stats.items()},
            }
            for h, stats in sorted(hourly.items(), key=lambda kv: -kv[1]["cost"])[:12]
        ],
    }


def _fleet_main(argv: list[str]) -> int:
    """Parse fleet flags, run :func:`fleet_census`, print the report."""
    flags = {
        "--sessions-dir": "~/.omp/agent/sessions",
        "--provider": "",
        "--model": "",
        "--since": "",
        "--until": "",
    }
    exclude: list[str] = []
    index = 0
    while index < len(argv):
        flag = argv[index]
        if flag in flags:
            index += 1
            if index >= len(argv):
                print(f"{flag} needs a value", file=sys.stderr)
                return 2
            flags[flag] = argv[index]
        elif flag == "--exclude":
            index += 1
            if index >= len(argv):
                print("--exclude needs a value", file=sys.stderr)
                return 2
            exclude.append(argv[index])
        index += 1

    result = fleet_census(
        Path(flags["--sessions-dir"]).expanduser(),
        provider=flags["--provider"],
        model=flags["--model"],
        since=flags["--since"],
        until=flags["--until"],
        exclude=tuple(exclude),
    )
    totals = result["totals"]

    if "--json" in argv:
        print(json.dumps(result, indent=2))
        return 0

    window = (
        " -> ".join(x for x in (flags["--since"], flags["--until"]) if x) or "all time"
    )
    scope = (
        "/".join(x for x in (flags["--provider"], flags["--model"]) if x)
        or "all providers"
    )
    print(f"fleet census: {scope}, {window}, {result['files_scanned']} files scanned")
    print(
        f"  calls={totals['calls']} cost=${totals['cost']:.2f} cacheRead={totals['cache_read'] / 1e6:.1f}M"
        f" input={totals['input'] / 1e6:.1f}M output={totals['output'] / 1e6:.1f}M"
        f" stopError={totals['stop_error']}"
    )
    print(
        f"  first-after-switch: {totals['first_after_switch_calls']} calls"
        f" ${totals['first_after_switch_cost']:.2f}"
    )
    print("  categories:")
    for name, stats in result["categories"].items():
        print(f"    {name:20} ${stats['cost']:8.2f} ({stats['calls']} calls)")
    d = result["duplicates"]
    print(f"  duplicate calls: ~{d['extra_calls']} extra, ~${d['est_cost']:.2f}")
    print("  top sessions:")
    for s in result["top_sessions"][:8]:
        print(f"    ${s['cost']:8.2f} {s['calls']:5d} calls  {s['file'][:58]}")
    print("  top intents:")
    for i in result["top_intents"][:10]:
        print(f"    ${i['cost']:7.2f} x{i['calls']:4d}  {i['intent']}")
    return 0


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__.strip().splitlines()[8], file=sys.stderr)
        return 2

    if "--fleet" in argv:
        return _fleet_main([a for a in argv[1:] if a != "--fleet"])

    path = Path(argv[1]).expanduser()
    as_json = "--json" in argv[2:]
    try:
        items = load(path)
    except (OSError, ValueError) as error:
        print(f"{path}: {error}", file=sys.stderr)
        return 2

    findings, evicted_tokens = census(items)
    total = sum(len(refs) for refs in findings.values())

    if as_json:
        print(
            json.dumps(
                {
                    "items": len(items),
                    "waste": findings,
                    "evicted_tokens": evicted_tokens,
                },
                indent=2,
            )
        )
        return 0

    print(f"{path.name}: {len(items)} items, {total} waste events\n")
    for name in (
        "eviction",
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
