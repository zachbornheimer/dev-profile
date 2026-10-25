---
name: 00 Opportunity Discovery
description: Find places in existing code where software already needs bounded semantic understanding, and translate that need into a Choice, Score, or Noul question instead of treating the cookbook catalog as a whitelist.
---

ORIGINAL SOURCE: https://docs.typesafe.ai/concepts/use-case-map
VIDEO: none
Use the original source primarily. This skill below is a summary in our own words. View details at this link.

## When to use

Before deciding TypeSafe doesn't apply to a codebase because no cookbook title matches it. Use whenever code sends prose to an LLM and then parses the reply back into a label, a boolean, a score, or a routing decision.

## What it demonstrates

The use-case map groups TypeSafe applications into five categories — AI automation software (code owns control flow, not markdown files), real-time applications (frontier intelligence at ~150ms), AI map-reduce over big data, universal verification (jailbreaks, citation errors, hallucinations, mistakes), and harness engineering (model routing, semantic context retrieval, LLM error detection) — then breaks the underlying work into nine recurring decision shapes: classification, detection, scoring, routing, search & retrieval, ranking, verification, ML feature extraction, and structured data extraction. The page lists 21 domain-specific applications spanning recruiting, customer support, financial crime detection, legal compliance, e-commerce, moderation, advertising, gaming, insurance claims, and knowledge-graph construction — illustrations of the shapes, not an exhaustive whitelist.

## Steps / call shape

Ask one question of any code path that turns unstructured text into a decision: is the output space bounded even though the input is unstructured? If yes, map the existing shape onto a primitive:

```text
LLM prompt "return one of these labels"      -> Choice
LLM prompt "return true/false"               -> Noul
LLM prompt "rate 1-5"                        -> Score
LLM returns JSON only so code can branch     -> Choice + Nouls/Scores
regex/keywords infer intent                  -> Choice/Noul after deterministic preprocessing
embeddings/BM25 produce candidates            -> per-candidate Score or Choice
multiple model calls resend the same document -> one batched System One call
```

Decompose rather than replace wholesale — a prompt asking an LLM to return department, urgency, refund-requested, and escalation as one JSON blob becomes four independent questions (`department`: Choice, `urgency`: Score, `refund_requested`: Noul, escalation facts: narrow Nouls) plus a code-owned escalation rule, because generation was being used only as a transport mechanism for bounded judgments.

## Results / numbers

The source page is a categorical map, not a benchmark — it reports five use-case categories, nine decision shapes, and 21 domain applications, with no cost or latency numbers of its own.

## Pitfalls

- Do not search only for code that already resembles a published cookbook; search for the underlying shape (bounded output space, unstructured input) instead.
- TypeSafe is usually the wrong fit for exact parsing with a stable grammar, database lookups, arithmetic or formal validation, open-ended prose/code generation, tool execution or authorization, or a reasoning step whose answer space can't be usefully bounded.
- Keep deterministic preprocessing (regex, database lookups) in code and hand TypeSafe only the remaining semantic ambiguity — don't ask a question code could already answer exactly.

## Related cookbooks

- `01-When-to-Use-TypeSafe.md` — the decision rule for choosing code vs. TypeSafe vs. a generative LLM once an opportunity is found here.
- `03-Atomic-Questions.md` — how to decompose a discovered opportunity into independent, inspectable questions.
- `13-Question-Parallel-Set.md` — batching the questions this discovery process surfaces into one call.
