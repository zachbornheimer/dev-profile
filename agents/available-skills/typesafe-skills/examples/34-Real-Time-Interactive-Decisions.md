---
name: 34 Real Time Interactive Decisions
description: Use TypeSafe to turn interactive product input into a bounded state change, route, or UI behavior through batched typed judgments, without generating conversational prose for decisions that don't need it.
---

ORIGINAL SOURCES:

- <https://docs.typesafe.ai/concepts/use-case-map>
- <https://docs.typesafe.ai/demos/smart-home>
- <https://docs.typesafe.ai/patterns/fan-out>

This is a cross-cutting pattern with no single source page; it draws on the three pages above.
VIDEO: Loom embed on the smart-home demo page (<https://www.loom.com/embed/18c4dbcf8db546dfb2d7f2ef018e78e4>), titled "TypeSafe Smart Home Demo." The share page did not load a description or transcript at fetch time — do not infer video content beyond the title.
Use the original source primarily. This skill below is a summary in our own words. View details at this link.

## When to use

An interactive product needs fast language understanding to pick a bounded state change, route, or UI behavior — not a chatbot reply. Use this for smart-home controls, in-app natural-language commands, game actions, UI shortcuts ("show me failed payments from enterprise customers"), live moderation signals, or adaptive interfaces choosing among known views.

## What it demonstrates

The `demos/smart-home` Vite/React single-page app takes a command like "Turn off all lights" and evaluates every plausibly relevant classification question up front in one API call (speculative fan-out), rather than asking questions sequentially and only issuing the next one once the prior answer narrows things down. It pairs TypeSafe with a generative LLM: TypeSafe handles deterministic operations (parsing the command, categorizing the request), while the LLM is reserved for open-ended work TypeSafe can't do — splitting compound requests and generating conversational responses. `patterns/fan-out` is the general form of that same technique (see `06-Speculative-Fan-Out.md`).

## Steps / call shape

```text
user input + current application state
  -> batched TypeSafe judgments (including speculative ones)
  -> deterministic state transition / UI update
```

```python
if category.choice == "bug_report":
    if bug_severity.score > 1.5 and bug_repro.noul > 0.6:
        escalate_to_engineering(ticket_id, severity="high")
```

The smart-home demo asks its full set of classification questions on every command, even ones likely to be irrelevant for that particular request, then filters in code after the response comes back — optimizing for one round trip rather than for the smallest possible number of questions asked.

## Results / numbers

No cost/accuracy table is published for the smart-home demo itself; `patterns/fan-out`'s support-ticket example is the quantified version of the same technique (see `06-Speculative-Fan-Out.md` for its numbers). The demo's stated finding is qualitative: minimizing question count by asking sequentially "ends up being much slower and more expensive than batching all questions into one upfront API call."

## Pitfalls

- Speculative fan-out trades a few unused/irrelevant answers per call for eliminating round-trip latency — that trade only pays off because parallel questions in one call add little to response time; sequential follow-up calls do not get that benefit.
- Over-speculating with many implausible questions still burns tokens without benefit — restrict fan-out to genuinely plausible branches, not every conceivable one.
- Reserve the generative LLM for what it's actually needed for (splitting compound requests, conversational phrasing) — routing plain classification through it defeats the purpose of the pattern.

## Related cookbooks

- `06-Speculative-Fan-Out.md` — the general pattern and its quantified support-ticket example.
- `10-Smart-Home-Assistant.md` — the fuller worked version of this specific demo.
