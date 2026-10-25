---
name: 32 AI Harness and Model Routing
description: Use TypeSafe for the fast, deterministic-orchestration decisions inside an AI harness — routing to a handler, estimating risk, selecting context, verifying tool-call intent — so expensive model tokens are spent only where generation is actually required.
---

ORIGINAL SOURCES:

- https://docs.typesafe.ai/concepts/use-case-map
- https://docs.typesafe.ai/patterns/intent-routing
- https://docs.typesafe.ai/cookbooks/skill_suggestion
- https://docs.typesafe.ai/cookbooks/llm_guardrails

This is a cross-cutting pattern with no single source page; it draws on the four pages above.
VIDEO: none
Use the original source primarily. This skill below is a summary in our own words. View details at this link.

## When to use

An AI harness (agent runtime, assistant, copilot) repeatedly spends expensive-model tokens on decisions that don't require generation: which handler or model to use, how relevant a piece of context is, whether a tool call matches user intent, whether a response has a known failure mode. Use TypeSafe for exactly those decisions and reserve the expensive model for genuine generation.

## What it demonstrates

`intent-routing` classifies an incoming request (e.g. customer message intent and complexity) with parallel `Choice`/`Score` questions and routes deterministic lookups away from any LLM entirely, sending only the harder categories to a specialist model, gated by confidence. `skill_suggestion` solves harness context selection at scale: with a 182-skill catalog, a cheap wide-ranking `Choice` plus three `Noul` gate questions score every skill, then a narrower verification pass re-examines the top 3 candidates with full descriptions before suggesting (or declining to suggest) one skill to load into the system prompt. `llm_guardrails` (see `31-Universal-Verification-Layer.md`) supplies the verification stage — inspecting a harness's own tool calls or generated replies for known failure modes before code decides whether to execute or emit them.

## Steps / call shape

```text
request
  -> TypeSafe routing + risk + context judgments
  -> code selects deterministic handler / model / skill
  -> expensive model only where needed
  -> TypeSafe verification
  -> code accepts or escalates
```

```json
{
  "intent": {
    "type": "choice",
    "instructions": "The primary intent of this customer message",
    "criteria": {
      "order_status": "Asking about an existing order",
      "product_question": "Asking about a product before buying",
      "return_exchange": "Wants to return or exchange something",
      "complaint": "Unhappy with experience, wants resolution"
    }
  },
  "complexity": {
    "type": "score",
    "instructions": "How complex is this request to resolve",
    "criteria": ["Simple lookup", "Requires judgment", "Unusual situation"]
  }
}
```

```python
def suggest(request: str) -> tuple[str, ...]:
    """At most one skill name for a request, or () for 'nothing here applies'."""
    wide = rank_wide(request)
    if wide["gate"] < GATE_THRESHOLD:
        return ()
    shortlist = tuple(name for name, _ in wide["ranked"][:SHORTLIST])
    result = rerank(request, shortlist, EXCERPT_CHARS)
    if max(result["fits"].values()) < FITS_THRESHOLD:
        return ()
    return (result["winner"],)
```

Model selection is never itself authorization — execution permissions stay explicit in code/policy, downstream of the routing decision.

## Results / numbers

Skill suggestion, tested on 488 requests against `claude-haiku-4-5-20251001` over Nous Research's 182-skill Hermes catalog:

| Metric | Baseline | With TypeSafe suggestion | Oracle ceiling |
|---|---|---|---|
| Wrong loads | 16.8% | 7.3% | 2.5% |
| Needless loads | 9.8% | 4.0% | 1.2% |

2.3x fewer wrong loads, 2.4x fewer needless ones; the suggestion fixed 37 previously-wrong requests but broke 7 previously-correct ones.

## Pitfalls (AgentMux relevance flagged)

- A confident wrong suggestion is more persuasive than no suggestion at all — the skill-suggestion cookbook explicitly reports it *breaks* some previously-correct baseline selections, not only fixes wrong ones. **AgentMux relevance:** any skill/tool auto-suggestion layer built this way needs to measure regressions, not just gains.
- The gate threshold (mean of the three wide `Noul` questions) and the shortlist size (3 candidates) both need calibration per catalog size; a much larger roster than 182 skills may need hierarchical ranking instead of one flat wide pass.
- The suggestion-block wording is a measured cache key, not decorative prose — editing it invalidates cached rankings.
- Confidence thresholds in intent routing must be set per decision's stakes; low confidence on a critical routing decision should trigger human review, not silent automation.

## Related cookbooks

- `09-Intent-Routing.md`, `17-Function-Calling.md`, `18-Skill-Suggestion.md` — the individual full worked examples this file summarizes together.
- `31-Universal-Verification-Layer.md` — the verification stage this harness pattern relies on before accepting a tool call or generated output.
