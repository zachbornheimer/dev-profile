---
name: 19 Entity Alignment
description: Decide whether two candidate entity records describe the same product using one ordered Score plus companion field-match Nouls, so a costly false merge, a safe reject, and an ambiguous curator case are all distinguishable.
---

ORIGINAL SOURCE: <https://docs.typesafe.ai/cookbooks/entity_alignment>
VIDEO: none
Use the original source primarily. This skill below is a summary in our own words. View details at this link.

## When to use

Matching candidate records across two catalogs or knowledge graphs, where merging two different entities is far more expensive than leaving a real duplicate unmerged — so a binary same/different decision hides too much risk.

## What it demonstrates

The cookbook aligns candidate entity pairs from two beer catalogs. Each pair gets one `Score` question with three ordered levels, plus three companion `Noul` questions (same name? same brewery? same style?) that explain — without changing — the primary route.

```python
LEVELS = {
    0: "They describe two different products",
    1: "They describe closely related products that may or may not be the same",
    2: "They describe one and the same product",
}

Score(
    instructions="How do the two entity descriptions relate as products?",
    criteria=LEVELS,
)
```

The decision rule rounds the returned score: `min(int(score_value + 0.5), len(LEVELS) - 1)`.

## Steps / call shape

```text
deterministic blocking -> candidate pairs -> Score (3 levels) + 3 Nouls -> route
  level 0 -> leave unlinked
  level 1 -> curator queue
  level 2 -> assert sameAs
```

Cheap deterministic blocking produces candidate pairs first; TypeSafe judges only plausible pairs, never all-pairs matching across the full catalogs. Install: `pip install matplotlib ipython 'cooksafe>=0.2.0,<0.3.0'`. Requires `TYPESAFE_API_KEY`; caches to `json_cache.json` by default.

## Results / numbers

On 450 candidate pairs:

| Outcome        | Count | Share |
| -------------- | ----- | ----- |
| assert sameAs  | 40    | 8.9%  |
| curator queue  | 50    | 11.1% |
| leave unlinked | 360   | 80.0% |

## Pitfalls

- The cut points at 0.5 and 1.5 are not tuned parameters — they fall out of the level wording itself. What decides a pair is which side of a cut point it lands on, not how near it sits to a level.
- Changing the middle-level description changes the split between curator queue and unlinked pairs, so treat that wording as a policy decision, not incidental copy.
- A `Choice` would hide the ordering relationship between the three outcomes; a binary `Noul` would force threshold engineering to invent the middle state. Use `Score` specifically because the outcomes are ordered from reject to review to merge.
- Run TypeSafe only over pairs that already survived deterministic blocking — sending every possible pair is not what this pattern demonstrates and is not what the cost numbers assume.

## Related cookbooks

- `08-Composite-Scoring.md` — another use of ordered Score levels to encode asymmetric-cost decisions.
- `19-Entity-Alignment.md` companion pattern `20-Classify-RAG-Passages.md` — narrow per-item Noul batteries used as explanatory signals alongside a primary routing decision.
- `36-Manual-Review-to-Confidence-Gated-Automation.md` — the general pattern of routing ambiguous cases to human review instead of forcing a binary automated decision.
  </content>
