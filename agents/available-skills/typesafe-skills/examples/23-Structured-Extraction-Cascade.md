---
name: 23 Structured Extraction Cascade
description: Extract with a cheap mini model first, verify each field with a batched TypeSafe error battery returning calibrated P(wrong), and escalate to an expensive reasoning model only when a field-level signal fires above threshold.
---

ORIGINAL SOURCE: https://docs.typesafe.ai/cookbooks/sde_cascade
VIDEO: none
Use the original source primarily. This skill below is a summary in our own words. View details at this link.

## When to use

Structured extraction where most records are easy and correct, but a schema-valid extraction can still be semantically wrong (hallucinated, off-target, or incomplete) — and you want reasoning-model quality without paying reasoning-model cost on every record.

## What it demonstrates

The cookbook runs a two-rung cascade tested on 100 ScrapeGraphAI extraction prompts. Rung 0 extracts with `gpt-5.4-mini` ($0.75/$4.50 per 1M input/output tokens). A TypeSafe verifier (`jev-1.12`, $0.042/$0.00 per 1M tokens — free output) checks each field with a battery of yes/no questions returning calibrated P(wrong). Only records with a flagged field escalate to `gpt-5.5` ($5.00/$30.00 per 1M tokens) as rung 1.

```python
fired = {qid: p for qid, p in checks.items() if p > FIRE_THRESHOLD}
if fired:
    return expensive_extract(...)
return cheap_record
```

## Steps / call shape

```text
source + schema
  -> cheap extractor (rung 0)
  -> TypeSafe semantic verifier (per-field battery)
      clean   -> keep cheap extraction
      flagged -> expensive reasoning extractor (rung 1)
```

Verification questions for non-empty fields: `name_desc_mismatch`, `type_mismatch`, `unreasonable`, `hallucinated`, `off_target`, `incomplete`, `format_violation`. For empty fields: `absence_wrong` (does the source contain information that should have been extracted?). Aggregation is `max` across fields — escalate if *any* field flag exceeds the 0.7 fire threshold, since averaging would let one strong error signal get diluted into silence. Install: `pip install openai datasets jsonschema ipython 'cooksafe>=0.2.0,<0.3.0'`. Requires `OPENAI_API_KEY` and `TYPESAFE_API_KEY`.

## Results / numbers

On the 100-prompt ScrapeGraphAI test set, the cascade achieves roughly 0.81 quality — most of the pure reasoning-model quality — at roughly $0.10 per extraction, sitting on the pareto frontier up-and-left of every single-model baseline (cheap rung handles easy items near-free; only flagged items pay reasoning-model cost).

## Pitfalls

- Structured-output/JSON-mode validation is not a substitute for this verifier: schema violations are rare and largely synthetic, while semantic errors (hallucinations, off-target extractions) are the real failure mode this pattern targets.
- Frame every verifier question as "bad = TRUE" with explicit criteria — an escalation signal should fire on the error case, not require inverting a "is this correct?" answer.
- Use `max`, not mean, to aggregate per-field P(wrong) — averaging one serious error against several clean fields would silently suppress the escalation.
- Keep the verifier independent and cheap; if it becomes as expensive as the reasoning model, the cascade's cost advantage disappears.

## Related cookbooks

- `21-Verify-Citations.md` — the same cheap-check-then-verify shape, applied to citations instead of extracted fields.
- `28-Classification-Using-Confidence.md` — using calibrated confidence to decide when a cheap classification needs escalation.
- `16-Recover-Document-Structure.md` — another pattern where a second pass depends on the first pass's output, though here the second pass is a fallback rather than a required stage.
</content>
