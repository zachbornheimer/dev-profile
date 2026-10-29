---
name: 36 Manual Review to Confidence Gated Automation
description: Identify a queue of humans repeatedly reading text into a bounded set of outcomes, encode the policy as typed judgments, automate the clear cases, and reserve human attention for uncertain or high-risk ones.
---

ORIGINAL SOURCES:

- <https://docs.typesafe.ai/concepts/use-case-map>
- <https://docs.typesafe.ai/patterns/confidence-routing>
- <https://docs.typesafe.ai/cookbooks/consistency_noul_cookbook>
- <https://docs.typesafe.ai/cookbooks/classification_using_confidence>

This is a cross-cutting pattern with no single source page; it draws on the four pages above.
VIDEO: none
Use the original source primarily. This skill below is a summary in our own words. View details at this link.

## When to use

Humans repeatedly read text and choose from a small set of outcomes — support ticket routing, insurance claim screening, compliance triage, fraud alert prioritization, listing review, recruiting screening — and the policy for those decisions can be made explicit. Use this to automate the clear cases and reserve reviewer time for the ambiguous or consequential ones, not to eliminate reviewers.

## What it demonstrates

`patterns/confidence-routing` sets the general rule: confidence is a second axis alongside the answer itself — "the answer tells you what; confidence tells you whether to act" — with different thresholds for different risk tiers (e.g. 0.6 for a low-stakes balance check, 0.85 for auto-approving a transfer, with a confirmation step in between). `consistency_noul_cookbook` measures how trustworthy that confidence signal is: on a 14-question auto-insurance claim rubric repeated 15 times, TypeSafe's `Noul` mean per-question standard deviation was 0.0102, versus far higher and inconsistent variance from generative LLMs even at temperature 0 — and it adds an explicit uncertainty band (0.30–0.70) that routes borderline probabilities to human review instead of forcing a binary decision near 0.5. `classification_using_confidence` (see `28-Classification-Using-Confidence.md`) is the applied instance: SEC filing classification that backs off to a broader label instead of guessing when confidence is low.

## Steps / call shape

```text
record + evidence
  -> atomic TypeSafe judgments
  -> code policy
      clear / low-risk -> automate
      uncertain        -> human review
      high-risk        -> specialist review
```

```python
if action.confidence < 0.6:
    route_to_support_agent(account_id)
elif action.choice == "check_balance":
    show_balance(account_id)
elif action.choice == "approve_transfer":
    if action.confidence > 0.85:
        approve_transfer(account_id)
    else:
        ask_user_to_confirm(prompt)
```

```python
def noul_decision_with_uncertainty(probability: float) -> str:
    if probability < 0.30:
        return "no"
    if probability > 0.70:
        return "yes"
    return "uncertain"  # escalate to human review
```

## Results / numbers

Self-consistency cookbook, 14-question rubric over one complex auto-insurance claim, 15 repeated runs:

| Metric                               | Result                                |
| ------------------------------------ | ------------------------------------- |
| TypeSafe latency                     | 111ms per 14-question call            |
| Speed vs. generative LLMs            | 10–125x faster (non-reasoning models) |
| Cost vs. generative LLMs             | 22–806x cheaper (historical pricing)  |
| Mean per-question standard deviation | 0.0102                                |

Confidence-gated routing example thresholds: 0.6 floor for low-stakes actions, 0.6–0.85 requires confirmation, >0.85 auto-approves high-stakes actions.

## Pitfalls

- A hard 0.5 cutoff treats 0.49 and 0.51 as opposite decisions despite near-identical uncertainty — the uncertainty band (e.g. 0.30–0.70) exists specifically to avoid that brittleness.
- Requesting a specific model version (e.g. `jev-latest`) can silently resolve to a different underlying version over time; check returned model metadata rather than assuming the requested alias is stable.
- Confidence thresholds are calibrated per decision's stakes and per corpus — the 0.6/0.85 example values and the 0.30–0.70 uncertainty band are illustrative, not universal defaults.
- The purpose is to reserve reviewer attention for ambiguous or consequential cases, not to eliminate reviewers — keep the decision criteria observable so the automated tier stays auditable.

## Related cookbooks

- `28-Classification-Using-Confidence.md` — the applied single-level backoff instance of this pattern.
- `07-Confidence-Gated-Routing.md` — the general confidence-routing pattern this file draws its core code shape from.
- `11-Self-Consistency-Nouls.md`, `12-Self-Consistency-Choices.md` — the reliability measurements behind trusting a confidence threshold at all.
