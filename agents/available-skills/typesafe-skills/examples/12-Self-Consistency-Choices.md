---
name: 12 Self Consistency Choices
description: Run a deliberately borderline moderation post through an 8-question Choice rubric 15 times across TypeSafe and several LLMs to measure label agreement, automatic-action coverage, and cost/speed at a chosen confidence threshold.
---

ORIGINAL SOURCE: https://docs.typesafe.ai/cookbooks/consistency_choice_cookbook
VIDEO: none
Use the original source primarily. This skill below is a summary in our own words. View details at this link.

## When to use

A `Choice` classification feeds an automatic action, and the question is not just "which label wins" but "how much of the traffic can safely be automated at a given confidence threshold."

## What it demonstrates

The cookbook evaluates one intentionally fence-sitting moderation post — heated language, insults, an off-platform link, prior strikes, and user reports, with "no single obvious answer" — through an 8-question Choice rubric (content category among None/Harass/Hate/Violence/Spam/Sexual, primary moderation risk, target of content, enforcement action needed, queue assignment, link handling, review pathway, overall severity) run 15 independent times per condition, each with a unique UID. Conditions: TypeSafe `jev-latest` (sampled 2026-09-11), non-reasoning LLMs `claude-haiku-4-5` and `gpt-5.4-mini` (temperature 0, default, and single-pick), and reasoning LLMs `gpt-5.5` and `claude-opus-4-8` (default temperature only). Setup: `pip install anthropic openai matplotlib ipython 'cooksafe>=0.2.0,<0.3.0'`, with TypeSafe, Anthropic, and OpenAI API keys set.

## Steps / call shape

```python
answer = response.answers["moderation"]

if answer.confidence < AUTO_THRESHOLD:      # 0.60 in this cookbook
    return "uncertain"
return answer.choice
```

Measure two separate things on a representative dataset: whether the winning label stays stable across repeated calls, and — at the chosen confidence policy — what fraction of cases can be acted on automatically. Raising the threshold trades automation coverage for a safer automatic subset.

## Results / numbers

Cost and speed, per 8-question call, averaged across 15 runs:

| Condition | Time/call | Cost/call | Slower than TypeSafe | Costlier than TypeSafe |
|---|---|---|---|---|
| TypeSafe (`jev-latest`) | 114ms | $0.000046 | — | — |
| claude-haiku-4-5, t=0 | 3853ms | $0.003498 | 33.8x | 76.1x |
| gpt-5.5 (reasoning) | 12978ms | $0.041255 | 113.7x | 897.4x |

Decision agreement at a 0.60 probability threshold: TypeSafe reached 99.2% policy agreement, with 74.2% of cases resolved automatically and 25.8% marked uncertain; `claude-haiku-4-5` (t=0) reached 100% agreement but 0% abstention (never flagged uncertainty); `gpt-5.4-mini` (t=default) reached 84.2% agreement with 77.5% automatic. TypeSafe's mean probability standard deviation across labels was 0.0098, favorable against five of the six LLM conditions — but "close probabilities still permit routing changes: TypeSafe flips on 2 of the 8 questions," and no condition showed conflicting concrete labels across repeats on any question. Two questions (`primary_risk`, `link_handling`) consistently returned below-threshold probabilities for TypeSafe on this post.

## Pitfalls

- High repeatability is not the same as correctness — this cookbook measures consistency, not accuracy against a ground-truth label.
- Temperature 0 does not guarantee stability across all models; some conditions still disagreed with themselves run to run.
- A model that never abstains (100% agreement, 0% uncertain) isn't necessarily better — it means it never flagged its own uncertainty, which removes the review signal the threshold is meant to produce.
- Treat `uncertain` as an application outcome, not a model label — keep the model's closed set focused on the semantic classification and let code decide when it's trustworthy enough to act on.

## Related cookbooks

- `07-Confidence-Gated-Routing.md` — the routing mechanism this cookbook's 0.60 threshold feeds into.
- `11-Self-Consistency-Nouls.md` — the same stability-measurement method applied to Noul instead of Choice.
- `13-Question-Parallel-Set.md` — the batching mechanism behind running 8 questions per call here.
