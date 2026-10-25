---
name: 11 Self Consistency Nouls
description: Repeat a batched 14-question Noul rubric on one insurance claim across TypeSafe and several LLMs to measure answer stability, cost, and speed, and to size an uncertainty band around the 0.5 decision threshold.
---

ORIGINAL SOURCE: https://docs.typesafe.ai/cookbooks/consistency_noul_cookbook
VIDEO: none
Use the original source primarily. This skill below is a summary in our own words. View details at this link.

## When to use

A production Noul decision applies a threshold to a probability, and values near that boundary matter — before trusting any single call's probability as ground truth.

## What it demonstrates

The cookbook runs one auto-insurance claim (collision coverage, $500 deductible, $10k limit; vehicle rear-ended in a spectator parking lot at a track-day event, not on the circuit; $3,250 claimed across four line items; auto-triage pre-approved without human review) through a 14-question Noul rubric — `covered`, `exclusion`, `on_circuit`, `deductible`, `docs_sufficient`, `within_limit`, `within_window`, `reported_timely`, `rental_eligible`, `fraud_flag`, `human_review`, `manual_review`, `line_items_sum`, `subrogation` — 15 times per condition. Conditions include TypeSafe (`jev-latest`), non-reasoning LLMs (`claude-haiku-4-5`, `gpt-5.4-mini` at temperature 0 and default, plus a yes/no-only mode), and reasoning LLMs (`gpt-5.5`, `claude-opus-4-8`). Setup: `pip install anthropic openai matplotlib ipython 'cooksafe>=0.2.0,<0.3.0'`, with `TYPESAFE_API_KEY`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` set.

## Steps / call shape

```python
p = response.answers["covered"].noul

if 0.30 <= p <= 0.70:
    return human_review()
return "yes" if p > 0.70 else "no"
```

1. Define each yes/no proposition so `true` has one consistent meaning.
2. Batch the whole rubric in one request per sample.
3. Repeat representative states during evaluation to measure answer stability.
4. Inspect mean, spread, and how often values cross the operational threshold.
5. Create an explicit uncertain interval when the cost of a boundary error is high.

## Results / numbers

Per-query cost and speed, measured against TypeSafe (`jev-latest` at 111ms / $0.000043):

| Condition | Time/call | Cost/call | Speed vs TypeSafe | Cost vs TypeSafe |
|---|---|---|---|---|
| claude-haiku-4-5, t=0 | 1780ms | $0.001798 | 16.0x | 42.2x |
| claude-haiku-4-5, t=default | 1644ms | $0.001798 | 14.8x | 42.2x |
| claude-haiku-4-5, yes/no, t=0 | 1485ms | $0.001650 | 13.4x | 38.8x |
| gpt-5.4-mini, t=0 | 1405ms | $0.001089 | 12.7x | 25.6x |
| gpt-5.4-mini, t=default | 1177ms | $0.001179 | 10.6x | 27.7x |
| gpt-5.4-mini, yes/no, t=0 | 1113ms | $0.000950 | 10.0x | 22.3x |
| gpt-5.5 (reasoning) | 11125ms | $0.033157 | 100.2x | 778.9x |
| claude-opus-4-8 (reasoning) | 13886ms | $0.034275 | 125.0x | 805.1x |
| **typesafe_noul** | **111ms** | **$0.000043** | **1.0x** | **1.0x** |

TypeSafe's mean per-question probability standard deviation across the 15 repeats was 0.0102, below every LLM probability condition. Even TypeSafe's own values drifted across the 0.5 threshold in places — `covered` ranged 0.43–0.53 and `exclusion` ranged 0.53–0.62 across repeats — motivating the 0.30–0.70 uncertain band. The LLM conditions moved more, and moved even at temperature 0: "the LLM answers move from run to run, at temperature 0 too, and on the judgment calls the models disagree with themselves."

## Pitfalls

- Do not hide uncertainty by converting probabilities to hard booleans too early — keep the original Noul values in logs and downstream evaluation so a boundary case can be audited later.
- The published 0.30–0.70 uncertain band is an experiment-specific policy fit to this claim's error costs, not a default threshold to copy — fit the band to your own calibration.
- Even at temperature 0, non-reasoning and reasoning LLMs both showed run-to-run disagreement on judgment calls — temperature 0 alone doesn't buy determinism.

## Related cookbooks

- `05-Confidence-and-Probabilities.md` — Noul returns P(true) with no separate confidence field; this cookbook is the empirical case for treating that probability as unstable near 0.5.
- `12-Self-Consistency-Choices.md` — the same stability-measurement method applied to Choice classification instead of Noul.
- `13-Question-Parallel-Set.md` — the batching mechanism this cookbook relies on to run 14 questions per call.
