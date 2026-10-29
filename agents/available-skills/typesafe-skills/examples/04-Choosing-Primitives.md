---
name: 04 Choosing Primitives
description: Pick Choice, Score, Noul, or Box by the output shape the next line of code needs — closed-set label, ordered level, probability, or image edges.
---

ORIGINAL SOURCE: <https://docs.typesafe.ai/primitives>
VIDEO: none
Use the original source primarily. This skill below is a summary in our own words. View details at this link.

## When to use

While defining any TypeSafe question, before writing its `instructions` — the primitive choice determines what fields the answer carries and how code can act on it.

## What it demonstrates

TypeSafe has four question primitives. **Choice** answers "which of these options?" and returns `choice`, `probabilities`, and `confidence` — good for routing a ticket to a department, classifying a document type, or detecting a programming language. **Score** answers "which level?" and returns `score`, `legend`, `probabilities`, and `confidence` — suited to measurements on a spectrum like bug severity, customer frustration, or skill level. **Noul** answers "is this true?" and returns a single `noul` value from 0 to 1 representing a probability — appropriate for yes/no questions where the probability itself is the useful signal. **Box** answers "where is this in an image?" and returns four edges as fractions of width/height plus `confidence` — it needs Jev 1.14 and an image in the request; pair it with a presence Noul because Box has no "not found". Choice, Score, and Noul also accept images in state, instructions, or criteria when `TypeSafe-Danger-Zone-Images: true` is set. Sending every question that shares the same state in one request is close to free, since questions evaluate independently and in parallel.

## Steps / call shape

```python
from typesafe_sdk import Choice, Noul, Score, TypeSafeClient

response = client.system_one(
    state=your_data,
    questions={
        "department": Choice(
            instructions="Which handler best fits `message`?",
            criteria={
                "billing": "Charges, refunds, or subscriptions",
                "orders": "Shipping, cancellation, or returns",
                "other": "None of these clearly fit",
            },
        ),
        "severity": Score(
            instructions="How severe is the reported impact?",
            criteria=["minor inconvenience", "workflow blocked", "critical outage"],
        ),
        "refund_requested": Noul(
            instructions="Does `message` explicitly request a refund?"
        ),
    },
)

answer = response.answers["department"]  # .choice, .probabilities, .confidence
```

## Results / numbers

This is a reference page for the type system, not a benchmark — no cost or latency numbers are published here.

## Pitfalls

- Choice needs mutually exclusive, unordered options; add an escape option (e.g. `"other"`) when the list may be incomplete.
- Score needs each level defined in plain language rather than an unexplained number — scores can land between defined levels, which is useful for weighting and ranking.
- Noul's value near 0.5 means uncertainty about yes/no; it is not a medium point on a semantic scale — use Score for that instead.
- Pick the primitive whose answer feeds the next line of code without reinterpretation; if code has to translate the answer before using it, the wrong primitive was chosen.
- Box is not a decision primitive. Do not use it when code only needs yes/no or a label; use Noul or Choice on the image instead.
- Images and Box are experimental. Read `37-Images-and-Box.md` before sending pixels.

## Related cookbooks

- `05-Confidence-and-Probabilities.md` — reading `confidence` and `probabilities` off Choice/Score answers.
- `08-Composite-Scoring.md` — combining several Score answers into one weighted result.
- `13-Question-Parallel-Set.md` — mixing Noul, Choice, and Score questions in one batched call.
- `37-Images-and-Box.md` — opt-in images, limits, and Box pairing.
