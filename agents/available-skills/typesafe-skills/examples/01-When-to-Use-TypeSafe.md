---
name: 01 When To Use TypeSafe
description: Decide whether a workflow step belongs in deterministic code, TypeSafe's System One model, or a generative LLM before wiring up an integration.
---

ORIGINAL SOURCE: https://docs.typesafe.ai/introduction
VIDEO: none
Use the original source primarily. This skill below is a summary in our own words. View details at this link.

## When to use

Before adding TypeSafe to a workflow, or when replacing an existing LLM prompt that already returns JSON for code to parse.

## What it demonstrates

TypeSafe's Jev is a "System One model": instead of generating text for humans to read, it returns typed values and probability distributions software can consume directly. The introduction frames the mismatch it replaces — "you are coercing a text-generation system into outputting structured decisions, then parsing the results back into something your code can depend on" — and lays out three primitives (Choice, Score, Noul) that can be combined in a single call, evaluated in parallel, with no performance penalty for asking more questions. The core discipline is atomic, well-scoped questions: instead of "rate this startup," ask separately about market size, feasibility, and differentiation, then compose the results in application code with explicit weights.

## Steps / call shape

Route each decision to the component that owns it:

```text
input -> deterministic preparation -> TypeSafe judgment -> code policy -> action
                                                   \-> review / LLM fallback
```

- Use **ordinary code** when the answer follows from exact facts or formal rules.
- Use **TypeSafe** when software needs a bounded semantic judgment over unstructured text — routing, closed-set classification, rubric scoring, evidence checks, relevance judgments, policy checks, guardrails, confidence-aware escalation.
- Use a **generative LLM** when the output itself must be open-ended text, code, explanation, planning, or conversation.

Jev is not an agent loop — it does not choose tools autonomously or generate prose; it returns typed judgments for code to consume.

## Results / numbers

The introduction is conceptual and does not publish its own cost or latency figures; see `13-Question-Parallel-Set.md` and the self-consistency cookbooks (`11`, `12`) for measured numbers.

## Pitfalls

- Recognize the smell tests: "we ask an LLM to return one of these five labels," "we parse JSON out of a model response," "the regex finds candidates but can't tell which one the user meant," "most cases should be automated, but uncertain ones need review" — all point at TypeSafe, not at a bigger prompt.
- A generative model is still the right component when the product needs a paragraph, free-form text, code generation, or a conversational answer — don't force those into Choice/Score/Noul.
- Don't turn Jev into an agent loop; it decides and routes, it doesn't act autonomously.

## Related cookbooks

- `00-Opportunity-Discovery.md` — finding the candidate decision points this rule is applied to.
- `04-Choosing-Primitives.md` — once TypeSafe is the right tool, picking Choice vs. Score vs. Noul.
- `10-Smart-Home-Assistant.md` — a worked example pairing TypeSafe judgments with a generative LLM fallback.
