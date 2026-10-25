---
name: 15 Line by Line Semantic Search
description: Rank ID-tagged document lines with a Choice question while a companion Noul checks whether any line actually answers the query, so ranking-with-no-real-answer is distinguishable from a real hit.
---

ORIGINAL SOURCE: https://docs.typesafe.ai/cookbooks/semantic_find
VIDEO: none
Use the original source primarily. This skill below is a summary in our own words. View details at this link.

## When to use

You need to find which line, clause, or record in a document answers a plain-language query, and you need to know when the document simply doesn't contain an answer rather than accept the least-wrong match.

## What it demonstrates

The cookbook builds semantic search over GitHub's Terms of Service, tagging 218 lines with short IDs (e.g. `L052`) and sending one `Choice` question (which line answers the query) plus one `Noul` question (does any line address it) in a single request.

## Steps / call shape

```python
from typesafe_sdk import Choice, Noul, NoulCriteria, TypeSafeClient

TYPESAFE_MODEL = "jev-1.12"

def where_question(query: str) -> Choice:
    return Choice(
        instructions=f'Which line contains the answer to: "{query}"?',
        criteria={line_id(i): None for i in range(len(LINES))},
    )

def exists_question(query: str) -> Noul:
    return Noul(
        instructions=f'Does any line address: "{query}"?',
        criteria=NoulCriteria(
            true="At least one line states or directly implies the answer",
            false="No line addresses this",
        ),
    )

with TypeSafeClient() as client:
    result = client.system_one(
        state={"lines": tagged_lines},
        questions={"where": where_question(query), "exists": exists_question(query)},
    )
```

Install: `pip install 'cooksafe>=0.2.0,<0.3.0'`. Requires `TYPESAFE_API_KEY`.

## Results / numbers

Example thresholds used to interpret the `exists` Noul: `FOUND = 0.7`, `ABSENT = 0.35`. Observed behavior on the 218-line GitHub ToS test set:

- Direct answers: exists probability >= 0.9
- Missing answers: exists probability <= 0.05
- Partial answers: probabilities near the middle thresholds

## Pitfalls

- `Choice` probabilities are relative and always sum to one — some option ranks first even when every line is irrelevant, so `Choice` alone cannot signal "no answer here." Always pair it with the existence `Noul`.
- The cookbook's Choice option limit is 255 for its model/API configuration at time of writing — check the live docs before assuming this still holds for a new build.
- For documents beyond that option limit, use a two-pass search: a first Choice question selects a window, a second ranks within it — don't try to flatten every line into one call.
- This pattern generalizes to clauses, records, candidate facts, or UI elements — any finite set of pre-existing spans — but TypeSafe should only select; code owns the exact source text.

## Related cookbooks

- `14-Re-Rank-Search-Results.md` — scoring a shortlist of candidates from a separate retriever, rather than ranking every line in one document.
- `16-Recover-Document-Structure.md` — another pattern that uses line IDs as anchor text the model reads directly rather than rewrites.
- `20-Classify-RAG-Passages.md` — applying narrow per-passage checks after retrieval, the RAG-pipeline analog of this document-search pattern.
</content>
