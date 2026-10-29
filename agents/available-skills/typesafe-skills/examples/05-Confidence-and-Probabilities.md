---
name: 05 Confidence And Probabilities
description: Use the `confidence` field to gate actions by risk, and the full `probabilities` distribution when relative likelihoods matter, rather than treating every winning answer as equally trustworthy.
---

ORIGINAL SOURCE: <https://docs.typesafe.ai/confidence>
VIDEO: none
Use the original source primarily. This skill below is a summary in our own words. View details at this link.

## When to use

Whenever code acts on a Choice or Score answer without checking how certain the model was, or when tuning how aggressively to automate a decision.

## What it demonstrates

Choice and Score answers expose both `probabilities` (the full distribution across options or levels) and `confidence` (a single 0-1 number derived from how concentrated that distribution is — "concentrated on one outcome means a confident answer, spread out means an uncertain one"). For three options the confidence formula approximates `(3 × largest probability − 1) / 2`. Noul exposes P(true) directly and has no separate confidence field. The docs recommend a three-tier usage pattern: high confidence acts automatically, medium confidence proceeds with caution (confirm or flag), low confidence does not act (route to a human or an alternative system) — and different actions in the same system should be gated at different thresholds depending on consequence, since "if an intelligent system cannot express honest uncertainty, the system cannot be trusted."

## Steps / call shape

```python
answer = response.answers["intent"]

if answer.confidence < REVIEW_BELOW:
    return review()
return handlers[answer.choice]()
```

Use the full `probabilities` distribution instead of just `confidence` when relative probabilities matter — beam search, reranking, custom uncertainty metrics, or classical-ML features that consume the whole distribution.

## Results / numbers

This is a reference page for the confidence mechanism, not a benchmark. See `11-Self-Consistency-Nouls.md` and `12-Self-Consistency-Choices.md` for measured stability numbers at specific thresholds.

## Pitfalls

- Thresholds express policy, not a fixed constant — a read-only UI route can tolerate more ambiguity than approving money movement or deleting data; measure your own error tradeoffs rather than copying a docs example's threshold.
- Noul has no `confidence` field — the probability itself (`.noul`) is the signal; don't look for a `.confidence` attribute on a Noul answer.
- Don't discard the distribution and treat every winning choice as equally trustworthy — the model's uncertainty is part of the interface.

## Related cookbooks

- `07-Confidence-Gated-Routing.md` — a worked routing example built on this mechanism.
- `11-Self-Consistency-Nouls.md` / `12-Self-Consistency-Choices.md` — measuring how much a threshold choice actually buys in stability and automation coverage.
