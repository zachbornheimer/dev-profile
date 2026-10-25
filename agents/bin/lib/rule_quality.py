"""What makes a cass-memory rule worth keeping, and the two model passes that enforce it.

Extraction proposes rules with evidence quoted from the session; a separate judge
pass keeps only rules that clear every bar in JUDGE_CRITERIA. Both talk to the
model through plain prompts and parse JSON arrays from the reply.
"""

from __future__ import annotations

import html
import json
import os
import re
from dataclasses import dataclass

MAX_RULES = 3
RETIRED_TOOLS = tuple(
    t.strip()
    for t in os.environ.get("MEMORY_LEARN_RETIRED_TOOLS", "agentmux").split(",")
    if t.strip()
)
ELISION = re.compile(r"\.\.\.|…")
MIN_EVIDENCE_FRAGMENT = 8
HTML_TAG = re.compile(r"<[^>]+>")
BETTER_PRACTICE_MARK = "Better practice:"
MAX_BETTER_PRACTICE_CHARS = 300  # every stored character is paid for again at recall
FACT_VERDICTS = frozenset({"true", "false", "unverifiable"})
TYPOGRAPHY = str.maketrans({"’": "'", "‘": "'", "“": '"', "”": '"', "–": "-", "—": "-"})
QUOTED_SPAN = re.compile(r"'([^']{8,})'|\"([^\"]{8,})\"|“([^”]{8,})”")
CATEGORY_PREFIX = re.compile(r"^\s*\[[\w-]+\]\s*")

EXTRACTION_CONTRACT = f"""
## Output contract
Reply with ONLY a JSON array of at most {MAX_RULES} objects
{{"content": string, "category": string, "evidence": string}}.
- content: one rule naming a concrete tool, command, file, repo, or service, stating a fact
  a capable agent would NOT already know (a gotcha, a project convention, a verified fix).
- evidence: ONLY a short verbatim quote copied exactly from the session (command output,
  error, test result) that PROVES the rule. No commentary. It is checked mechanically
  against the session record; a paraphrase is rejected. An agent merely asserting
  something is not evidence.
Reject general engineering hygiene and anything the user simply told the agent.
Most sessions yield [] — return [] unless a rule clearly clears this bar.
"""

JUDGE_CRITERIA = f"""Keep a rule only if ALL hold:
1. Specific: names a concrete tool, command, file, repo, setting, or service.
2. Non-obvious: a capable senior engineer/agent would plausibly get this wrong without it.
   Generic practice fails even when it names a tool. DROP examples:
   - "Test shell functions in a fresh shell after editing ~/.zshrc" (standard practice)
   - "When renaming X across config files, update all of them consistently" (obvious)
   - "Invert the condition as well as the assertion when flipping a test" (generic)
   KEEP examples:
   - "eApp fields marked hidden=true never run their GetAnswer/SetAnswer hooks"
   - "Docker MCP catalog accepts only images or remote URLs, not npx servers"
3. Durable: still useful in a future session, not a detail of one finished task.
4. Not about retired tools: {", ".join(RETIRED_TOOLS) or "none"}.
5. Evidenced: the evidence shows the fact was observed, not just claimed.
   If evidence is "(none recorded)", judge the other criteria only.
6. Consistent and new: does not contradict the user's standing instructions below, and
   does not merely restate them (agents already load them every session)."""


@dataclass(frozen=True, slots=True)
class Rule:
    content: str
    category: str
    evidence: str = ""


def json_array(reply: str) -> list:
    """The first JSON array in a model reply, skipping prose or brackets before it."""
    decoder = json.JSONDecoder()
    for start in (i for i, ch in enumerate(reply) if ch == "["):
        try:
            items, _ = decoder.raw_decode(reply, start)
        except ValueError:
            continue
        if isinstance(items, list):
            return items
    raise ValueError(f"no JSON array in model reply: {reply[:200]!r}")


def parse_rules(reply: str) -> list[Rule]:
    """Proposed rules that carry evidence; strips a duplicated "[category]" prefix."""
    rules = [
        Rule(
            CATEGORY_PREFIX.sub("", str(i["content"])).strip(),
            str(i.get("category") or "general"),
            str(i.get("evidence", "")).strip(),
        )
        for i in json_array(reply)
        if isinstance(i, dict) and str(i.get("content", "")).strip()
    ]
    return [r for r in rules if r.evidence][:MAX_RULES]


def judge_prompt(rules: list[Rule], standing_instructions: str = "") -> str:
    listing = "\n".join(
        f"{n}. [{r.category}] {r.content}\n   evidence: {r.evidence or '(none recorded)'}"
        for n, r in enumerate(rules)
    )
    return (
        f"You review proposed memory rules for AI coding agents.\n{JUDGE_CRITERIA}\n\n"
        f"## User's standing instructions\n{standing_instructions or '(none provided)'}\n\n"
        f"Rules:\n{listing}\n\nBe strict: when in doubt, drop. Reply with ONLY a JSON "
        'array, one object per rule: {"index": int, "mistake_prevented": string, '
        '"keep": bool, "reason": string}. mistake_prevented names the concrete wrong '
        "action a capable agent would take without the rule; if you cannot name one, "
        "keep is false."
    )


def parse_verdicts(reply: str, count: int) -> list[tuple[bool, str]]:
    """(keep, reason) per rule index; a rule the judge skipped is rejected."""
    verdicts: list[tuple[bool, str]] = [(False, "no verdict")] * count
    for v in json_array(reply):
        if (
            isinstance(v, dict)
            and isinstance(v.get("index"), int)
            and 0 <= v["index"] < count
        ):
            verdicts[v["index"]] = (v.get("keep") is True, str(v.get("reason", "")))
    return verdicts


def _normalized(text: str) -> str:
    """Case-, whitespace-, and typography-insensitive (curly quotes, dashes, ellipsis)."""
    return " ".join(text.translate(TYPOGRAPHY).lower().split())


def evidence_fragments(evidence: str) -> list[str]:
    """The verbatim parts of an evidence string.

    Models often narrate around the quote ('X' — so Y); when quoted spans exist,
    only they must match. Each span may be elided with "...", and every fragment
    that survives must match verbatim, so invented evidence cannot pass.
    """
    spans = [next(g for g in m.groups() if g) for m in QUOTED_SPAN.finditer(evidence)]
    pieces = spans or [evidence.strip("\"'` ")]
    fragments = [_normalized(f) for piece in pieces for f in ELISION.split(piece)]
    return [f for f in fragments if len(f) >= MIN_EVIDENCE_FRAGMENT]


def evidence_found(rule: Rule, recorded: str) -> bool:
    """True when every verbatim fragment of the rule's evidence occurs in the record."""
    haystack = _normalized(recorded)
    fragments = evidence_fragments(rule.evidence)
    return bool(fragments) and all(f in haystack for f in fragments)


@dataclass(frozen=True, slots=True)
class FactCheck:
    """A web-verified verdict on one rule. verdict: true | false | unverifiable."""

    verdict: str
    better_practice: str = ""
    source: str = ""
    contradiction: str = ""

    @property
    def keep(self) -> bool:
        return self.verdict != "false"


def fact_check_prompt(rules: list[Rule]) -> str:
    listing = "\n".join(f"{n}. {r.content}" for n, r in enumerate(rules))
    return f"""Fact-check memory rules for AI coding agents against CURRENT official docs.
Use WebSearch/WebFetch for every rule about a public tool, service, or API. Rules about a
private codebase cannot be checked on the web: mark them "unverifiable".

For each rule decide:
- verdict: "true", "false" (wrong or outdated today), or "unverifiable".
- goal: the outcome an agent following this rule is pursuing (e.g. "keep dependencies
  current across many repos"). Reasoning only; it is not stored.
- better_practice: an imperative alternative ("Use X ..."), only if a materially better,
  widely recommended way to reach that goal exists (a different tool, a central/shared
  config, a newer platform feature), with its trade-off, at most {MAX_BETTER_PRACTICE_CHARS}
  characters. Never doubts, caveats, or restatements of the rule; when unsure, "".
- source: the URL that settled it ("" if unverifiable). Prefer official docs.
- contradiction: for "false" only, the exact sentence copied from the source that
  contradicts the rule. It is checked against the fetched page; without a real quote
  the verdict falls back to "unverifiable".

Rules:
{listing}

Reply with ONLY a JSON array, one object per rule:
{{"index": int, "verdict": string, "goal": string, "better_practice": string, "source": string,
"contradiction": string}}."""


def parse_fact_checks(reply: str, count: int) -> list[FactCheck]:
    """One FactCheck per rule; a rule the checker skipped is unverifiable, not false."""
    checks = [FactCheck("unverifiable")] * count
    for c in json_array(reply):
        if (
            isinstance(c, dict)
            and isinstance(c.get("index"), int)
            and 0 <= c["index"] < count
        ):
            verdict = str(c.get("verdict", "")).lower()
            checks[c["index"]] = FactCheck(
                verdict if verdict in FACT_VERDICTS else "unverifiable",
                str(c.get("better_practice") or "").strip(),
                str(c.get("source") or "").strip(),
                str(c.get("contradiction") or "").strip(),
            )
    return checks


def with_better_practice(rule: Rule, check: FactCheck) -> Rule:
    """The rule, extended with the better practice the fact-check found (and its source)."""
    if not check.better_practice:
        return rule
    cited = f" ({check.source})" if check.source else ""
    better = check.better_practice
    if len(better) > MAX_BETTER_PRACTICE_CHARS:
        better = better[: MAX_BETTER_PRACTICE_CHARS - 1].rsplit(" ", 1)[0] + "…"
    content = f"{rule.content} {BETTER_PRACTICE_MARK} {better}{cited}"
    return Rule(content, rule.category, rule.evidence)


def confirm_contradiction(check: FactCheck, source_page: str) -> FactCheck:
    """Keep a "false" verdict only if its quoted contradiction is really on the source page."""
    if check.verdict != "false":
        return check
    page_text = HTML_TAG.sub(" ", html.unescape(source_page))
    quoted = Rule("", "", check.contradiction)
    if check.contradiction and evidence_found(quoted, page_text):
        return check
    return FactCheck("unverifiable", check.better_practice, check.source)
