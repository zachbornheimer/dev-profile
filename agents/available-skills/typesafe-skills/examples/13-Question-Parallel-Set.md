---
name: 13 Question Parallel Set
description: Batch several independent TypeSafe questions over one shared document into a single System One call instead of one call per question, cutting cost and latency with no change in the answers.
---

ORIGINAL SOURCE: https://docs.typesafe.ai/cookbooks/parallel_questions
VIDEO: none
Use the original source primarily. This skill below is a summary in our own words. View details at this link.

## When to use

Several independent judgments (`Noul`, `Choice`, or `Score`) run over the same document or state, and none of the questions depends on another's answer. Use this whenever you find yourself sending the same large state to TypeSafe more than once in a request.

## What it demonstrates

The cookbook runs 13 independent compliance questions over a ~54,000-character Wikipedia article on the GDPR (General Data Protection Regulation), asking each set two ways: one batched `system_one` call carrying all 13 questions, and 13 separate single-question calls. It repeats both five times and shows the answers are identical either way — batching only changes cost and speed, never the result.

## Steps / call shape

```python
from typesafe_sdk import Choice, Noul, Score, TypeSafeClient

state = {"article": gdpr_wikipedia_text}  # 53,777 characters

questions = {
    # 8 Noul questions, e.g.:
    "breach_72h": Noul(
        instructions="Must a personal data breach be reported to the "
        "supervisory authority within 72 hours according to `article`?"
    ),
    # 2 Choice questions, e.g.:
    "max_fine": Choice(
        instructions="What is the maximum administrative fine for the "
        "most serious infringements described in `article`?",
        criteria={
            "TwentyM_or_4pct": "EUR 20 million or 4% of annual worldwide turnover, whichever is higher",
            "TenM_or_2pct": "EUR 10 million or 2% of annual worldwide turnover, whichever is higher",
            "other": "None of the above",
        },
    ),
    # 3 Score questions, e.g.:
    "compliance_burden": Score(
        instructions="How heavy is the compliance burden `article` places on organisations?",
        criteria=["Negligible", "Light", "Moderate", "Heavy", "Extreme"],
    ),
}

with TypeSafeClient() as client:
    # One call, all 13 questions:
    batched = client.system_one(state=state, questions=questions)

    # Compare against: 13 separate calls, one question each, same `state`
    # repeated in every call.
```

The comparison in the cookbook issues the batched call and the 13 individual calls five times each and diffs every answer.

## Results / numbers

Measured on `jev-1.12` ($0.042 per 1M input tokens, $0.00 per output token):

| Approach | Cost | Wall-clock time |
|---|---|---|
| 1 batched call (13 questions) | $0.000497 | 0.27 s |
| 13 individual calls | $0.006090 | 2.71 s |

Batching was **12.2x cheaper** and **10.0x faster**. Across all 5 repeated runs, batched and individual answers were identical — standard deviation across repeats was 0.0 for effectively every question, so batching added no extra noise.

## Pitfalls

- Running the 13 individual calls concurrently instead of serially would close some of the latency gap, but each call still re-sends the full 54K-character document, so it never recovers the cost advantage of sending the state once.
- Batching only helps when questions are genuinely independent. If one question's answer should change how a later question is asked, that's speculative fan-out (see `06-Speculative-Fan-Out.md`), not this pattern — batch the branches, not a true dependency chain.
- Don't copy the 12.2x/10.0x figures as guaranteed numbers for a different document, model, or question mix — they're a published example, not a constant.

## Related cookbooks

- `06-Speculative-Fan-Out.md` — batching questions whose branch isn't known yet, not just independent questions.
- `11-Self-Consistency-Nouls.md` and `12-Self-Consistency-Choices.md` — repeat a batched request to measure answer stability, the same experimental shape this cookbook uses to prove batching is noise-free.
- `33-Semantic-Map-Reduce.md` — applying the same narrow judgments across many records rather than many questions on one document.
