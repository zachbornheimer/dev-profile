---
name: 18 Skill Suggestion
description: Rank a large agent-skill roster cheaply in one TypeSafe call, re-check only the top 3 with full descriptions in a second call, and let the second call reject all candidates instead of forcing a guess.
---

ORIGINAL SOURCE: <https://docs.typesafe.ai/cookbooks/skill_suggestion>
VIDEO: none
Use the original source primarily. This skill below is a summary in our own words. View details at this link.

## When to use

An agent has a large skill/tool/policy catalog that's too expensive to inject in full, and truncated one-line descriptions make similar entries hard to tell apart, causing wrong or needless loads.

## What it demonstrates

The cookbook suggests one skill (or none) per turn to an agent running `claude-haiku-4-5-20251001`, using two TypeSafe requests over a 182-skill roster:

1. **Wide ranking:** one `Choice` question ranks all 182 skills from compact/truncated descriptions, plus three `Noul` gate questions decide whether any skill is needed at all. Returns the top 12 candidates and a gate score.
2. **Shortlist re-ranking:** a second request reads only the top 3 candidates with full descriptions and `SKILL.md` excerpts (700 chars each). A `Choice` picks the best match; individual `Noul` questions validate each candidate's fit.

The chosen suggestion — or none — is inserted into the agent's system prompt as one line:

```text
<skill_relevance>
Relevant to the current request: pptx-author. Ignore this if it does not fit what the user
actually asked for.
</skill_relevance>
```

**How the suggestion is produced and whether it is reusable:** it is exactly one skill name or empty, decided by two threshold checks on TypeSafe's own scores (`GATE_THRESHOLD` on the mean of the three gate nouls, `FITS_THRESHOLD` on the best per-candidate fit noul) — not a free-text recommendation. The `suggest(request)` function returns a tuple with at most one skill name; code inserts that name verbatim into the prompt block above. Because the block is a single fixed-format line that either names one skill or says none applies, and its own wording never changes turn to turn, it is reusable as-is by any agent harness that can splice a line into its system prompt — the roster text and the block format stay stable, which the cookbook calls out as preserving prefix cache integrity.

## Steps / call shape

```text
user turn + compact roster
  -> shortlist (top 12, gate score)
  -> detailed re-check of top 3 candidates
  -> zero or one suggestion
```

```python
SHORTLIST = 3  # candidates passed to stage 2
EXCERPT_CHARS = 700  # body text per skill for reranking
GATE_THRESHOLD = 0.30  # mean of three gate nouls; below = suggest nothing
FITS_THRESHOLD = 0.30  # best "does this fit" noul; below = reject shortlist
TYPESAFE_MODEL = "jev-1.12"  # ranking model
AGENT_MODEL = "claude-haiku-4-5-20251001"  # agent under test
```

Core functions: `rank_wide(request)` returns the ranked top-12 list, gate score, and individual noul values; `rerank(request, names, excerpt)` takes the shortlist tuple and excerpt length and returns the winner name, per-candidate fit scores, and timing; `suggest(request)` applies both thresholds and returns a tuple with at most one skill name; `suggestion_block(names)` formats that into the system-prompt block, or emits "No skill in the roster appears relevant" when empty.

## Results / numbers

Tested on 488 requests (315 with ground-truth skill coverage, 173 with none):

| Metric         | Baseline | TypeSafe | Oracle |
| -------------- | -------- | -------- | ------ |
| Wrong loads    | 16.8%    | 7.3%     | 2.5%   |
| Needless loads | 9.8%     | 4.0%     | 1.2%   |

2.3x fewer wrong loads, 2.4x fewer needless loads than baseline. Of the 315 covered requests, the suggestion fixed 37 the agent had gotten wrong, but broke 7 it had gotten right on its own.

## Pitfalls

- Wrong loads cluster in the same category as the correct skill — the ranking refines within a neighborhood rather than redirecting from a completely wrong area, so don't expect the gate alone to fix a systematically confused roster.
- Always include a "none applies" path on both stages — closed-set ranking without an escape hatch encourages false positives when the correct answer is no selection.
- Even a correct suggestion doesn't guarantee correct use: agents given the right skill still fail to load it about 2.5% of the time (the Oracle row), which sets a floor on achievable accuracy no amount of suggestion tuning removes.
- The suggestion fixed more cases than it broke (37 vs 7) but did break some — treat it as a probabilistic aid the agent can ignore, per the "Ignore this if it does not fit" wording, not a hard override.

## Related cookbooks

- `09-Intent-Routing.md` — choosing a handler, the same two-stage cheap-then-detailed shape applied to routing instead of skill selection.
- `17-Function-Calling.md` — a related closed-set selection problem (which function) with the same Choice-plus-gate architecture.
- `13-Question-Parallel-Set.md` — batching the gate and ranking questions into one call per stage, which is what keeps this pattern to two requests instead of many.
  </content>
