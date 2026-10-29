---
name: 14 Re-Rank Search Results
description: Narrow a corpus with cheap lexical or vector retrieval, then re-score only the shortlist with a TypeSafe Noul per query-candidate pair before final ranking, instead of asking TypeSafe to search the whole corpus.
---

ORIGINAL SOURCE: <https://docs.typesafe.ai/cookbooks/rerank_typesafe>
VIDEO: none
Use the original source primarily. This skill below is a summary in our own words. View details at this link.

## When to use

You already have a retriever (BM25 or vector search) producing a shortlist, but it overvalues wording overlap and needs a semantic re-score before you show or use the top results.

## What it demonstrates

The cookbook re-ranks legal search results on the CLERC dataset: 3,565 court opinion passages, 40 queries, top-30 shortlist per query from BM25/vector retrieval. Each of the 30 candidates in a shortlist gets one `Noul` question asking whether the candidate could be the cited precedent; candidates are then sorted by the returned probability.

## Steps / call shape

```text
query -> BM25/vector search -> top 30 candidates -> TypeSafe Noul per candidate -> sort by score
```

```python
from typesafe_sdk import Noul, TypeSafeClient


def rerank_question(query: str, candidate: str) -> Noul:
    return Noul(
        instructions=f'Could this candidate passage be from the cited precedent for: "{query}"?',
    )


with TypeSafeClient() as client:
    # One call per candidate in the shortlist (1,200 calls total: 40 queries x 30 candidates)
    scores = {
        c: client.system_one(
            state={"query": query, "candidate": c},
            questions={"match": rerank_question(query, c)},
        )
        for c in shortlist
    }
    ranked = sorted(shortlist, key=lambda c: scores[c]["match"], reverse=True)
```

Install: `pip install bm25s datasets matplotlib 'cooksafe>=0.2.0,<0.3.0'`. Model: `jev-1.12`.

## Results / numbers

Measured on the CLERC dataset (3,565 passages, 40 queries, 1,200 total re-rank calls, $0.0645 total):

| Metric          | Before re-rank | After re-rank |
| --------------- | -------------- | ------------- |
| Top-1 accuracy  | 5%             | 18%           |
| Top-5 accuracy  | 15%            | 35%           |
| Top-10 accuracy | 38%            | 62%           |

## Pitfalls

- Keep the first-stage retriever broad enough to preserve recall — re-ranking can only reorder what the retriever already surfaced.
- Cache stable query/candidate evaluations rather than re-scoring on every request.
- Measure latency across the whole shortlist, not one candidate, before committing to shortlist size.
- Use an explicit evidence/relevance criterion per question rather than a vague "is this good?" score.
- Don't copy the 5%->18%/15%->35%/38%->62% figures as guaranteed numbers for a different corpus or query mix — they're a published example, not a constant.

## Related cookbooks

- `15-Line-by-Line-Semantic-Search.md` — searching within a single document once retrieval has narrowed scope, using Choice plus an existence Noul instead of one Noul per candidate.
- `06-Speculative-Fan-Out.md` — batching questions whose branch isn't known yet.
- `13-Question-Parallel-Set.md` — batching independent questions into one call, relevant if companion questions accompany each re-rank candidate.
  </content>
