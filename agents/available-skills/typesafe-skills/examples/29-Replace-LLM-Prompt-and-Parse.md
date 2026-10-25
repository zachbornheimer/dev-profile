---
name: 29 Replace LLM Prompt and Parse
description: Recognize generative LLM calls whose real purpose is to emit a label, boolean, score, or bounded argument, and replace that transport layer with TypeSafe typed judgments instead of JSON parsing and repair.
---

ORIGINAL SOURCES:

- https://docs.typesafe.ai/concepts/how-to-build-with-system-one
- https://docs.typesafe.ai/cookbooks/function_calling
- https://docs.typesafe.ai/primitives

This is a cross-cutting pattern with no single source page; it draws on the three pages above.
VIDEO: none
Use the original source primarily. This skill below is a summary in our own words. View details at this link.

## When to use

A prompt asks a generative model to "return JSON," "respond with one of," "classify as," "return true or false," "rate from 1 to 5," or "choose the tool/function" — and downstream code then parses that output and branches on it. Use this whenever the real requirement is a bounded semantic decision, not open-ended generation.

## What it demonstrates

`how-to-build-with-system-one` frames the underlying philosophy: keep control flow, deterministic rules, and side effects in code, and break broad judgments into narrow typed questions with explicit instructions and criteria, rather than letting a model choose the next action (the agent pattern) or free-generate structured text. `primitives` supplies the three typed question shapes this replaces prompt-and-parse output with — `Choice` (pick one of a fixed list; returns `choice`, `probabilities`, `confidence`), `Score` (rate along ordered levels; returns `score`, `legend`, `probabilities`, `confidence`), and `Noul` (P(true) for a statement; returns a single 0–1 value). `function_calling` shows the concrete replacement of a natural-language-to-function-call mapping: type hints identify closed-set arguments, a spec file gives each argument a semantic description, and a dispatcher turns the spec into confidence-scored `Choice`/`Noul` questions instead of a model free-generating a function call.

## Steps / call shape

```text
Before: text -> generative LLM -> JSON parsing/repair -> validation -> branch
After:  text -> TypeSafe questions -> typed answers -> validation/policy -> branch
```

```python
def plot_price(
    symbol: Literal["SPY", "NVDA", "AMD", "AAPL", "MSFT", "TSLA"],
    style: Literal["line", "candles"] = "line",
    resolution: Literal["1m", "5m", "15m", "1h", "1d"] = "15m",
    include_volume: bool = False,
): ...

# "show me apple daily with volume"
# -> plot_price(symbol='AAPL', resolution='1d', include_volume=True)
```

Closed-set arguments (`Literal`, lists, booleans) become `Choice` or `Noul` questions generated from the function signature and a JSON spec file; free-text/numeric parameters fall back to their function defaults when unspecified. A request can mix both approaches:

```text
TypeSafe: decide whether the user needs a known action or free-form help
  known action -> deterministic handler
  free-form help -> generative LLM
```

## Results / numbers

The function-calling cookbook ran 10 trading functions (156,780 one-minute bars, 28 fillable arguments) against 14 natural-language test commands, generating 54 questions total. Tool-selection confidence ranged 0.53–1.00, averaging roughly 0.90. `how-to-build-with-system-one` cites System One's typed-question latency at roughly 100ms, suitable for real-time paths, versus reasoning-model generation.

## Pitfalls

- The opportunity is not "replace every LLM" — keep a generative model for fields that genuinely require open-ended text.
- "is amd tracking nvidia lately" scored only 0.82 confidence in the cookbook because the timeframe was ambiguous — omitting semantic context (e.g. "the one being measured" vs. "the yardstick") causes arguments to map to the wrong value.
- Computing overall call confidence as a product of individual question confidences masks one weak judgment among several strong ones — a minimum-confidence aggregate reflects call quality better than a product.

## Related cookbooks

- `17-Function-Calling.md` — the full worked function-calling example this file summarizes one layer up from.
- `30-Hybrid-Parsing-and-Semantic-Selection.md` — the companion pattern for when deterministic parsing, not generation, produces the candidates.
