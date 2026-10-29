---
name: 09 Intent Routing
description: Classify a request once with TypeSafe, then route it to deterministic code, a specialist LLM, or a human, so expensive resources are only invoked for the requests that actually need them.
---

ORIGINAL SOURCE: <https://docs.typesafe.ai/patterns/intent-routing>
VIDEO: none
Use the original source primarily. This skill below is a summary in our own words. View details at this link.

## When to use

Heterogeneous requests currently all flow through the same expensive model or handler, when most of them are simple enough for a cheaper, deterministic, or specialist path.

## What it demonstrates

"Classify incoming requests and route each to the optimal handler: deterministic logic, a specialist LLM, or a human." The pattern page's example is customer-service message routing that evaluates two questions in parallel: `intent` (Choice: order_status, product_question, return_exchange, complaint) and `complexity` (Score: simple lookup up through edge cases requiring escalation). Routing then combines both: low intent-confidence (below 0.5) goes to a human agent; complaints scoring above 1 on complexity trigger human review; everything else maps directly to a deterministic handler or a specialist LLM by intent type. "TypeSafe handles the classification all in a single quick call; the expensive resources only get invoked for the requests that actually need them."

## Steps / call shape

```text
request
  -> TypeSafe intent + complexity
      -> deterministic lookup
      -> specialist LLM
      -> workflow/function
      -> human review
```

```python
intent = response.answers["intent"]
complexity = response.answers["complexity"]

if intent.confidence < 0.5:
    return human_review()
if intent.choice == "complaint" and complexity.score > 1:
    return human_review()
return handlers[intent.choice]()
```

## Results / numbers

The pattern page does not publish measured cost/latency numbers for this specific routing example.

## Pitfalls

- Keep routing destinations explicit in the `Choice` criteria rather than inferring them elsewhere in code — the classifier and the handler map should stay in sync.
- Ask supporting questions like complexity or risk in the same call as intent, not a follow-up call, to keep the classification a single quick round trip.
- Low-confidence intent should route to review or clarification, not to whichever handler happened to win the Choice.

## Related cookbooks

- `06-Speculative-Fan-Out.md` — asking intent plus branch-specific follow-ups together in one call.
- `07-Confidence-Gated-Routing.md` — the confidence-threshold mechanism this pattern's 0.5 floor relies on.
- `10-Smart-Home-Assistant.md` — a worked demo combining intent routing with an LLM fallback for conversation.
