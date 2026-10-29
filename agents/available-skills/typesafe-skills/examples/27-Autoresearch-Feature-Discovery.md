---
name: 27 Autoresearch Feature Discovery
description: Use TypeSafe Noul/Score judgments as numeric features for a classical ML model, then let an LLM propose new questions from the model's residual errors instead of hand-engineering features.
---

ORIGINAL SOURCE: <https://docs.typesafe.ai/cookbooks/autoresearch_feature_discovery>
VIDEO: none
Use the original source primarily. This skill below is a summary in our own words. View details at this link.

## When to use

Free text needs to become numeric features for a classical supervised model, and manual feature engineering is slow or ceiling-limited. Use this when TypeSafe should act as a semantic feature extractor feeding a downstream model, rather than as the final predictor.

## What it demonstrates

The cookbook predicts wine review scores (80–100 scale) from tasting notes. An LLM proposes candidate `Score`/`Noul` questions (intensity and presence judgments), TypeSafe answers each question per row, a CatBoost regressor trains on the resulting numeric table, and the loop reads cross-validation errors and feature importances to propose revised or additional questions for the next round — repeated for 5 rounds.

## Steps / call shape

```text
text rows
  -> battery of Noul/Score questions
  -> numeric feature table
  -> classical supervised model
  -> error analysis
  -> propose better semantic questions
  -> repeat
```

```python
Score(
    instructions="How present is oak in this wine?",
    criteria=["Not present", "Barely present", "Moderate", "Strong", "Dominant"],
)
Noul(
    instructions="Is a fault mentioned?",
    criteria={"true": "Fault explicitly stated", "false": "No fault indicated"},
)

response = client.system_one(
    state=note,
    questions={"complexity": Score(...), "single_vineyard": Noul(...)},
    model="jev-1.12",
)
```

Each round, an LLM receives the current accepted questions, dev examples, and CV feedback (error history, importance scores), and returns up to 18 `add`/`revise`/`drop` actions against the question set. A `Score` contributes both its expected value and an uncertainty feature; a `Noul` contributes its P(true). Columns with spread under 0.05 are filtered automatically before training.

## Results / numbers

2,000 wine reviews (1,200 dev / 800 held-out), RMSE on an 80–100 scale (lower is better):

| Approach                                    | RMSE |
| ------------------------------------------- | ---- |
| Mean baseline                               | 3.09 |
| Word counts (CatBoost on text features)     | 2.47 |
| Ask score directly (single TypeSafe Score)  | 2.15 |
| Round 1 (18 questions, no feedback)         | 1.87 |
| Round 5 (38 questions, 4 refinement rounds) | 1.77 |

Round 1 to round 5 held-out improvement: −0.097 points, 95% CI [−0.147, −0.050]. Final model: 29 intensity (`Score`) questions producing 58 columns (mean + uncertainty) plus 9 presence (`Noul`) questions producing 9 columns. Top feature by importance share: `note_overall_tone_positivity` at 17.4%.

## Pitfalls

- Cost scales with row count, not question count — one TypeSafe request per row per round (2,000 rows = 2,000 requests per round), not per question.
- Round 5 began dropping more questions than it added — the search plateaus; watch for that as a stopping signal rather than running indefinitely.
- Keep train/validation/test boundaries strict: new question proposals must never see held-out labels or held-out error reports, or gains stop being reproducible.
- Cross-validated dev error sits above held-out error because dev models train on only 4/5 of dev rows versus 5/5 for the held-out score — don't compare the two numbers as if they used the same training set.

## Related cookbooks

- `33-Semantic-Map-Reduce.md` — the same "narrow judgment per record, aggregate outside the model" shape, applied more generally across large datasets.
- `28-Classification-Using-Confidence.md` — another example of using a TypeSafe signal (confidence) as an input to a code-side decision rather than the final answer.
