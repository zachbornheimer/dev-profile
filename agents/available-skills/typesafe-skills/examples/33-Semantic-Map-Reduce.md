---
name: 33 Semantic Map Reduce
description: Apply the same narrow TypeSafe judgment across many records, passages, or candidates in parallel, then aggregate the typed results with ordinary code — instead of asking SQL, regex, or embeddings alone to carry semantic meaning.
---

ORIGINAL SOURCES:

- https://docs.typesafe.ai/concepts/use-case-map
- https://docs.typesafe.ai/cookbooks/rerank_typesafe
- https://docs.typesafe.ai/cookbooks/autoresearch_feature_discovery

This is a cross-cutting pattern with no single source page; it draws on the three pages above.
VIDEO: none
Use the original source primarily. This skill below is a summary in our own words. View details at this link.

## When to use

A large dataset (records, passages, traces, documents) contains a semantic signal that SQL, regex, or embeddings alone can't recover reliably. Use this whenever you'd otherwise write one narrow semantic question and want to apply it at scale, then let ordinary data code do the aggregation, filtering, or statistics.

## What it demonstrates

`rerank_typesafe` re-ranks a BM25 shortlist of legal passages by asking one `Noul` question per query-candidate pair ("could this candidate passage be from the cited precedent?"), then sorting the shortlist by the returned probability — a map (per-pair judgment) followed by a reduce (sort). `autoresearch_feature_discovery` (see `27-Autoresearch-Feature-Discovery.md`) applies the same shape across an entire dataset of rows to build ML features rather than a ranking.

## Steps / call shape

```text
partition/candidate generation in code
  -> parallel TypeSafe judgments per record/chunk
  -> typed probabilities/scores
  -> deterministic aggregation, filtering, statistics, or ML
```

```python
is_cited_source = Noul(
    instructions="Could this candidate passage be from the cited precedent?",
    criteria=NoulCriteria(
        true="The candidate states the specific rule the query cites.",
        false="The candidate is only on a similar topic.",
    ),
)

nouls = {candidate: ask_typesafe(query, candidate) for candidate in shortlist}
reranked = sorted(shortlist, key=lambda c: nouls[c], reverse=True)
```

Design the question once and reuse the resulting typed signal across every record — keep batching, concurrency, retries, caching, and aggregation entirely outside the model, in code.

## Results / numbers

Re-ranking cookbook, 3,565 court opinion passages and 40 queries, BM25 shortlist of 30 candidates per query re-ranked by `Noul`:

| Metric | Before (BM25 only) | After (re-ranked) | Gain |
|---|---|---|---|
| Top-1 accuracy | 5% | 18% | +13pp |
| Top-5 accuracy | 15% | 35% | +20pp |
| Top-10 accuracy | 38% | 62% | +24pp |

Cost: 1,200 TypeSafe calls, 1.56M input tokens, $0.0645 total.

## Pitfalls

- Re-ranking only reorders the existing shortlist — it can never recover a candidate the fast search step missed entirely. The floor is set by recall, not by TypeSafe.
- Repeated calls on the same pair can produce slightly different `Noul` values due to model variance; don't treat a single re-rank as deterministic.
- Custom scoring criteria must be defined precisely enough that TypeSafe applies the same standard to every candidate — vague criteria degrade ranking consistency.
- Request volume scales with the number of items mapped, not the number of questions per item — plan cost per row, not per question.

## Related cookbooks

- `14-Re-Rank-Search-Results.md` — the full worked re-ranking example this file summarizes.
- `27-Autoresearch-Feature-Discovery.md` — the same map-reduce shape used to build ML features instead of a ranking.
