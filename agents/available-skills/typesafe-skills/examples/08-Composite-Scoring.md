---
name: 08 Composite Scoring
description: Score independent dimensions with separate Score questions, then combine normalized results with explicit code-owned weights instead of asking one prompt for an overall rating.
---

ORIGINAL SOURCE: <https://docs.typesafe.ai/patterns/composite-scoring>
VIDEO: none
Use the original source primarily. This skill below is a summary in our own words. View details at this link.

## When to use

Ranking or rating depends on several semantic dimensions that trade off differently for different purposes — for example, the same resume ranked differently for a senior IC role versus an engineering manager role.

## What it demonstrates

"Break a complex judgment into atomic scores, combine with weights you control in code." The pattern page's example scores a resume on four independent 0-4 dimensions — Python depth, team leadership, system design, and generalist capability — then normalizes each to 0-1 and combines them with role-specific weights: a Senior IC formula of 40% Python + 10% leadership + 40% design + 10% generalist, versus an Engineering Manager formula of 15% Python + 40% leadership + 20% design + 25% generalist. The same four semantic evaluations feed two different business policies without re-running any judgment.

## Steps / call shape

```python
quality = response.answers

technical = quality["technical_depth"].score / 4
leadership = quality["leadership"].score / 4
architecture = quality["architecture"].score / 4
generalist = quality["generalist"].score / 4

senior_ic = (
    0.40 * technical + 0.10 * leadership + 0.40 * architecture + 0.10 * generalist
)
eng_manager = (
    0.15 * technical + 0.40 * leadership + 0.20 * architecture + 0.25 * generalist
)
```

## Results / numbers

The pattern page publishes the weighting formulas above as its worked example; it does not report cost or latency numbers of its own.

## Pitfalls

- Avoid a single prompt like "give this candidate an overall score" when the real policy has separate dimensions — that hides both the model's error and the business tradeoff inside one opaque number.
- Low-confidence dimensions can and should be gated, down-weighted, or sent for review explicitly rather than folded silently into the weighted sum.
- Weight changes are then code changes under normal review, not prompt rewrites — keep the weights out of the question instructions.

## Related cookbooks

- `03-Atomic-Questions.md` — the decomposition discipline this pattern applies specifically to Score questions.
- `04-Choosing-Primitives.md` — why Score (not Choice or Noul) is the right primitive for each dimension here.
