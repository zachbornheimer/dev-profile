---
name: 28 Classification Using Confidence
description: Run one fine-grained Choice classification, then deterministically back off low-confidence winners to an existing parent category instead of making a second model call or escalating to a human.
---

ORIGINAL SOURCE: https://docs.typesafe.ai/cookbooks/classification_using_confidence
VIDEO: none
Use the original source primarily. This skill below is a summary in our own words. View details at this link.

## When to use

Labels form a hierarchy, and the same winning fine-grained category can be safely reported at a broader level when the model is unsure. Use this whenever "less specific but reliable" beats either guessing the narrow label or rejecting the result outright.

## What it demonstrates

The cookbook classifies SEC annual-report filings into 75 industry groups (rolling up into 10 broader divisions) using a single `Choice` call. When the returned `confidence` is at or above 0.9, the narrow group is reported; below that, code deterministically maps the winning group to its parent division instead of asking a second question.

## Steps / call shape

```python
QUESTION = (
    "Which broad industry does this company operate in? Judge the company's own operations "
    "as this filing describes them."
)

def questions() -> dict:
    return {
        "group": Choice(
            instructions=QUESTION,
            criteria={group: describe(group) for group in sorted(GROUPS)},
        )
    }

def classify(filing: dict) -> dict:
    answer = ask(filing["id"], filing["text"])
    sure = answer["confidence"] >= CONFIDENT  # CONFIDENT = 0.9
    return {
        "level": "group" if sure else "division",
        "label": answer["group"] if sure else division(answer["group"]),
        "confidence": answer["confidence"],
        "group": answer["group"],
    }
```

`confidence` comes back alongside the winning `Choice` option — high when nearly all probability mass landed on one option, low when it spread across several. Backing off to the parent requires no additional semantic judgment because code already knows the taxonomy.

## Results / numbers

Across 60 SEC filings with a 0.9 confidence threshold and taxonomy built from `sic_codes.tsv` (444 industries, 75 major groups, 10 divisions):

| Strategy | Accuracy |
|---|---|
| Always name a group, confident cases (n=30) | 90% (27/30) |
| Always name a group, unsure cases (n=30) | 40% (12/30) |
| Report division when unsure (n=30) | 70% (21/30) |
| Overall useful answers | 80% (48/60) |

## Pitfalls

- The 60 filings were pre-filtered to cases where the filer's own text supports their chosen code — the numbers measure this recipe's effectiveness on self-consistent text, not raw EDGAR metadata quality.
- The 0.9 confidence cutoff happened to split this test set roughly in half; a different corpus needs its own calibration, not this exact number.
- The approach assumes a hierarchical taxonomy — a flat label set has no parent to back off to.
- Development-stage companies describing planned businesses, and post-divestiture filers, are the cases that naturally produce lower confidence — expect the backoff to trigger disproportionately there.

## Related cookbooks

- `26-Hierarchical-Classification.md` — the multi-level version of this idea, using `Choice` probability distributions for beam search across an entire tree instead of a single confidence-gated backoff.
- `07-Confidence-Gated-Routing.md` — confidence used to choose an action tier (auto/confirm/escalate) rather than a taxonomy level.
