---
name: 22 LLM Guardrails
description: Screen both inputs and outputs with a battery of parallel hazard Nouls plus a severity Score in one request, then apply readable pass/review/block/support routing policies in code instead of a system prompt or cascading LLM calls.
---

ORIGINAL SOURCE: https://docs.typesafe.ai/cookbooks/llm_guardrails
VIDEO: none
Use the original source primarily. This skill below is a summary in our own words. View details at this link.

## When to use

You need an explicit, tunable safety layer around a generative LLM — one where thresholds and hazard definitions are reviewable code, not buried in a system prompt or the model's own weights.

## What it demonstrates

The cookbook screens both the user's message and the model's reply with one TypeSafe request per message: a set of hazard `Noul` questions (jailbreak/instruction override, request for harm or illegal assistance, medical diagnosis/dosage request, self-harm indicators) plus one `Score` question rating potential harm (No harm / Mild / Serious / Severe).

```python
HAZARD_ACTION = {
    "jailbreak": "block",
    "harmful_request": "block",
    "medical_advice": "review",
    "self_harm": "support",
}

POLICIES = {
    "strict": {"review_threshold": 0.35, "action_threshold": 0.70, "severity_block": 2.0},
    "permissive": {"review_threshold": 0.35, "action_threshold": 0.85, "severity_block": 2.0},
}
```

## Steps / call shape

```text
user input -> TypeSafe guard -> generator -> TypeSafe guard -> user
```

Two thresholds per hazard control escalation: scores above `review_threshold` trigger human review, scores above `action_threshold` trigger the hazard's configured action (`block` or `support`). The severity `Score` can override a review into a block. Routing actions are `pass` (no hazards triggered), `review` (human evaluation), `block` (refuse the turn), and `support` (crisis intervention path). Install: `pip install ipython 'cooksafe>=0.2.0,<0.3.0'`. Requires `TYPESAFE_API_KEY`; cached results shown are from `jev-1.12`, dated 2026-08-15.

## Results / numbers

The cookbook documents the architecture and its two named policies (`strict`, `permissive`) rather than a benchmark accuracy table — the two places meant to be edited per deployment are the hazard question dictionary and the named routing policies.

## Pitfalls

- A single "is this safe?" question hides *why* a request is risky — decompose into separate hazard signals so different hazards can use different thresholds and routes.
- Centralize hazard definitions, thresholds, severity rules, and pass/review/block/support decisions in code — never let the policy live only in a prompt.
- Do not assume the cookbook's exact hazards or thresholds fit another product; build the taxonomy around your actual policy, threat model, and review process.
- Severity can override a review to a block — make sure that override path is itself reviewable, not a hidden side effect of the severity Score.

## Related cookbooks

- `20-Classify-RAG-Passages.md` — the same battery-of-Nouls-plus-threshold-routing shape, applied to retrieved passages instead of chat turns.
- `07-Confidence-Gated-Routing.md` — the general confidence-threshold routing pattern this guardrail layer specializes.
- `36-Manual-Review-to-Confidence-Gated-Automation.md` — migrating a manual review queue into confidence-gated automation, the same shape as the review/block split here.
</content>
