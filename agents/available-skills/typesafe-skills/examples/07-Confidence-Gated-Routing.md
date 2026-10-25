---
name: 07 Confidence Gated Routing
description: Treat a Choice answer and its confidence as two separate routing inputs, so higher-consequence actions require a higher confidence threshold before executing automatically.
---

ORIGINAL SOURCE: https://docs.typesafe.ai/patterns/confidence-routing
VIDEO: none
Use the original source primarily. This skill below is a summary in our own words. View details at this link.

## When to use

An automated action has real consequences if the model's interpretation is wrong, and different actions in the same system carry different levels of risk.

## What it demonstrates

"The answer tells you what; confidence tells you whether to act." The pattern page's example is a voice-banking interface with three routing paths: confidence below 0.6 escalates to a human support agent regardless of intent; low-stakes actions like balance checks execute at 0.6+ confidence; high-stakes actions like transfers require 0.85+ confidence to execute automatically, or ask the user to confirm in the 0.6–0.85 range. "The 0.6 floor catches anything the model is genuinely uncertain about." Each action type keeps its own calibrated threshold matched to its consequences, rather than one global cutoff.

## Steps / call shape

```python
intent = response.answers["intent"]

if intent.confidence < MIN_CLASSIFICATION_CONFIDENCE:      # 0.6 floor
    return human_review()

if intent.choice == "read_balance":
    return show_balance()

if intent.choice == "approve_transfer":
    if intent.confidence >= TRANSFER_AUTO_THRESHOLD:        # 0.85+
        return confirm_and_execute()
    return ask_for_confirmation()                            # 0.6-0.85
```

## Results / numbers

The pattern page states thresholds as a worked example (0.6 floor, 0.85 auto-approve for transfers) rather than as measured benchmark output — no cost/latency table is published on this page. See `12-Self-Consistency-Choices.md` for a measured relationship between a chosen confidence threshold and automation coverage.

## Pitfalls

- Set thresholds according to consequence, not convenience — a docs example's 0.6/0.85 numbers are illustrative, not a default to copy for a different action.
- Prefer reversible behavior at lower confidence (confirm, gather evidence) over an irreversible automatic action.
- Log the answer, confidence, action taken, and eventual outcome so thresholds can be tuned from real data rather than guessed once and left alone.
- Don't discard confidence and treat every winning choice as equally trustworthy — that's the whole point of the pattern.

## Related cookbooks

- `05-Confidence-and-Probabilities.md` — the underlying confidence mechanism this pattern gates on.
- `09-Intent-Routing.md` — a related pattern that routes on intent type and complexity, also confidence-gated.
- `12-Self-Consistency-Choices.md` — measuring how a chosen confidence threshold trades automation coverage for safety.
