#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Bounded, active-only cm recall shared by SessionStart and Hermes."""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from hook_common import Decision, HookEvent, run_hook

HOOK_NAME = "memory-recall"
CM_BIN_ENV = "HC_CM_BIN"
DEFAULT_CM_BIN = "cm"
RULE_LIMIT = 5
SEARCH_LIMIT = 50
SIMILARITY_THRESHOLD = 0.3
CM_TIMEOUT_SECONDS = 8.0
MAX_RESPONSE_CHARS = 1_000_000
MAX_CONTEXT_CHARS = 2400
MAX_RULE_CHARS = 700
MAX_QUERY_CHARS = 600
LOGGER = logging.getLogger(__name__)
HEADER = "Relevant cm memory (retrieval hints, not approvals; provenance: cm why <id>):"
TOPICS = {
    "resume": (r"\b(restart(?:ed)?|reboot|resume|recover|interrupted)\b|please continue|assume.session", "computer restart recover interrupted session objective accepted decisions side effects"),
    "objective": (r"\b(objective|remember|original goal|accepted plan)\b", "remember original objective why accepted plan purge dev-profile"),
    "identity": (r"wrong dir|\b(takeover|resumption|session id|task id|assume.session)\b", "session takeover reconcile task session id named project wrong directory cwd"),
    "contract": (r"\b(atask|contract|handoff|superseded|lineage)\b", "atask contract handoff dated design lineage accepted contract superseded drafts"),
}
UNTRUSTED_INSTRUCTIONS = re.compile(r"<[^>]+>|ignore (?:all|previous)|system.prompt|you must|approved|run this", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class Rule:
    id: str
    content: str


def recall_topics(intent: str) -> frozenset[str]:
    """Treat intent as search data only; never copy it into model context."""
    if UNTRUSTED_INSTRUCTIONS.search(intent):
        return frozenset()
    return frozenset(name for name, (pattern, _) in TOPICS.items() if re.search(pattern, intent[:MAX_QUERY_CHARS], re.IGNORECASE))


def recall_query(cwd: str, intent: str = "", project: str = "") -> str:
    topics = recall_topics(intent)
    label = project if re.fullmatch(r"[\w.-]{1,80}", project) else Path(cwd).name
    return " ".join([*(TOPICS[t][1] for t in TOPICS if t in topics), label])[:MAX_QUERY_CHARS]


def records(value: object, key: str) -> list[dict[str, object]]:
    if not isinstance(value, dict) or value.get("success") is not True:
        return []
    data = value.get("data")
    rows = data.get(key) if isinstance(data, dict) else None
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        return []
    return rows


@dataclass(frozen=True, slots=True)
class Playbook:
    """The process seam; both calls share one bounded recall budget."""
    binary: str
    timeout: float = CM_TIMEOUT_SECONDS

    def read(self, args: list[str], key: str) -> list[dict[str, object]]:
        try:
            done = subprocess.run([self.binary, *args, "--json"], capture_output=True, text=True, timeout=self.timeout / 2, check=False)
            if done.returncode or len(done.stdout) > MAX_RESPONSE_CHARS:
                return []
            return records(json.loads(done.stdout), key)
        except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
            LOGGER.warning("cm recall %s failed: %s", args[0], type(exc).__name__)
            return []

    def similar(self, query: str, topics: frozenset[str] = frozenset()) -> list[Rule]:
        # cm's getActiveBullets includes drafts; similar omits state entirely.
        catalog = self.read(["ls"], "bullets")
        active = {row["id"]: row for row in catalog if isinstance(row.get("id"), str) and row.get("state") == "active" and row.get("deprecated") is False and row.get("maturity") != "deprecated"}
        if not active:
            return []
        matches = self.read(["similar", query, "--limit", str(SEARCH_LIMIT), "--threshold", str(SIMILARITY_THRESHOLD)], "results")
        selected: list[Rule] = []
        seen: set[str] = set()
        for match in matches:
            ident, content = match.get("id"), match.get("content")
            if not isinstance(ident, str) or not re.fullmatch(r"[\w-]+", ident) or ident in seen:
                continue
            row = active.get(ident)
            if row is None or not isinstance(content, str) or row.get("content") != content:
                continue
            if row.get("scope") == "task" and row.get("scopeKey") not in topics:
                continue
            if row.get("scope") not in {"global", "task"}:
                continue
            if not content.strip() or len(content) > MAX_RULE_CHARS:
                continue
            seen.add(ident)
            selected.append(Rule(ident, content))
            if len(selected) == RULE_LIMIT:
                break
        return selected


def render_rules(rules: list[Rule]) -> str:
    lines = [HEADER]
    for rule in rules[:RULE_LIMIT]:
        line = f"- [{rule.id}] {rule.content}"
        if len("\n".join([*lines, line])) <= MAX_CONTEXT_CHARS:
            lines.append(line)
    return "\n".join(lines) if len(lines) > 1 else ""


def recall_context(cwd: str, intent: str = "", project: str = "", playbook: Playbook | None = None) -> str:
    book = playbook or Playbook(os.environ.get(CM_BIN_ENV, DEFAULT_CM_BIN))
    return render_rules(book.similar(recall_query(cwd, intent, project), recall_topics(intent)))


def intent_text(payload: Mapping[str, object]) -> str:
    return " ".join(value for key in ("task_intent", "prompt", "user_message") if isinstance(value := payload.get(key), str))[:MAX_QUERY_CHARS]


def decide(event: HookEvent, playbook: Playbook | None = None) -> Decision | None:
    cwd = event.field("cwd", "cwd")
    if not cwd:
        return None
    intent = intent_text(event.payload)
    if not intent and event.field("source", "source") in {"resume", "compact"}:
        intent = "recover interrupted session"
    context = recall_context(cwd, intent, event.field("project", "project"), playbook)
    return Decision.context(context, event_name="SessionStart", log_label="emitted") if context else None


if __name__ == "__main__":
    run_hook(HOOK_NAME, decide)
