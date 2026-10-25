---
name: 17 Function Calling
description: Map a natural-language request to a typed function call by turning the function name and each closed-set argument into TypeSafe questions, so the model only selects from values the function can actually accept.
---

ORIGINAL SOURCE: https://docs.typesafe.ai/cookbooks/function_calling
VIDEO: none
Use the original source primarily. This skill below is a summary in our own words. View details at this link.

## When to use

Your application already has ordinary functions with bounded arguments, and natural language needs to select among them — a trading command, a plotting request, or any utterance that should resolve to one typed call.

## What it demonstrates

The cookbook turns trading commands like "plot rolling correlation between nvda and spy for the past month" into `rolling_correlation(symbol='NVDA', benchmark='SPY', window='1mo')` with confidence 0.91, tested across 14 commands against functions such as:

```python
def plot_price(
    symbol: Literal["SPY", "NVDA", "AMD", "AAPL", "MSFT", "TSLA"],
    resolution: Literal["1m", "5m", "15m", "1h", "1d"] = "15m",
    include_volume: bool = False,
): ...
```

## Steps / call shape

```text
utterance -> route/function Choice + argument questions -> validate -> ordinary function call
```

A spec file defines one `question` (primary selection) plus a `stated` question (did the user mention this argument at all) per parameter. A `Literal` becomes a `Choice`; a boolean becomes a `Noul` or two-option `Choice`; a list of allowed literals gets one yes/no per member using `{}` placeholder syntax when multi-select is required. The dispatcher expanded the cookbook's function set into 54 questions per command, with a `__tool__` question selecting the function itself.

## Results / numbers

Across the 14 test commands: confidence range 0.53-1.00. The system correctly disambiguated multi-ticker requests ("compare nvda amd and msft"), interpreted semantic variations ("is amd tracking nvidia lately" -> `rolling_correlation`), and omitted optional arguments when the user never stated them, preserving the function's own defaults.

## Pitfalls

- Confidence reports the *weakest* argument judgment across the whole call, not the product of all of them — don't average it away.
- Arguments without a closed set (free numbers, dates, free text) keep the function's own defaults; TypeSafe only fills closed-set arguments.
- Do not invoke a consequential tool merely because a function name won the routing Choice — gate low-confidence routing or dangerous arguments, ask for confirmation, and reject argument combinations that violate the function's real constraints.
- Keep execution, authorization, defaults, cross-field validation, and side effects in code, never in the model.
- This is preferable to asking a generative model to emit arbitrary JSON, because the model here only selects from values the function can accept — it can't hallucinate a field.

## Related cookbooks

- `09-Intent-Routing.md` — choosing a handler, the same routing shape this cookbook applies to whole functions.
- `13-Question-Parallel-Set.md` — the batching technique behind sending 54 questions in one request instead of one call per argument.
- `18-Skill-Suggestion.md` — a related selection problem (which skill, not which function) using a similar Choice-plus-gate shape.
</content>
