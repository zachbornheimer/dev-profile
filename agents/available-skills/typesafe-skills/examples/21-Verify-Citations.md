---
name: 21 Verify Citations
description: Check exact quote existence deterministically in code first, then use a TypeSafe Choice question to judge whether the surrounding source context supports, contradicts, or says nothing about the generated claim.
---

ORIGINAL SOURCE: https://docs.typesafe.ai/cookbooks/citation_check
VIDEO: none
Use the original source primarily. This skill below is a summary in our own words. View details at this link.

## When to use

An LLM has produced claims with citations, and you need to catch fabricated quotes, contradicted assertions, and citations that don't actually support what they're attached to.

## What it demonstrates

The cookbook verifies 8 citations against RFC 7519 (JSON Web Token). Step one is deterministic: normalize whitespace and curly quotes, then substring-search for the exact quote, classifying it `found`, `section-only` (no quote given), or `missing` (fabricated). Step two, for surviving citations, asks a `Choice` question about how the source section relates to the claim: `supports`, `contradicts`, or `says_nothing`.

```python
def locate(sections: dict[str, str], citation: dict) -> tuple[str, str | None]:
    """Returns status ('found', 'section-only', 'missing') and section text"""

def check_citation(sections: dict[str, str], citation: dict) -> dict:
    """Orchestrates string match + semantic verification.
    Returns: verdict, confidence, and auto/review flag"""

RELATION_TO_VERDICT = {
    "supports": "verified",
    "contradicts": "contradicted",
    "says_nothing": "unsupported",
}
```

## Steps / call shape

```text
citation
  -> exact source lookup (deterministic, no API call)
      missing -> fabricated
      found   -> TypeSafe Choice: supports / contradicts / says_nothing
                    -> verified / contradicted / unsupported
```

Four possible verdicts total: verified, fabricated, contradicted, unsupported. The `AUTO_ACCEPT` threshold (default 0.8) decides whether a verdict stands automatically (>= 0.8) or routes to a human reviewer (< 0.8). Install: `pip install ipython 'cooksafe>=0.2.0,<0.3.0'`. Requires `TYPESAFE_API_KEY`; results replay from `json_cache.json`.

## Results / numbers

On the 8-citation RFC 7519 test set:

| Category | Count | Confidence |
|---|---|---|
| Verified | 4 | 0.93-0.99 |
| Fabricated (string match caught) | 1 | n/a — no API call needed |
| Contradicted | 1 | 0.99 |
| Unsupported | 2 | 0.27, 0.56 (routed to review) |

## Pitfalls

- Exact string matching only — truncated or reworded quotes are marked fabricated even if the underlying claim is fine; production systems needing fuzzy tolerance require separate matching logic.
- `load_source()` and `split_sections()` in the cookbook are written for RFC structure specifically; other document formats need their own parsing.
- Verdict quality depends directly on how well source sections are defined — a quote can be word-for-word correct while the nearby text narrows, negates, or contradicts the claim, which string matching alone can never catch.
- Start `AUTO_ACCEPT` high and lower it only as trust builds with your specific documents — don't copy the 0.8 default without validating it against your own corpus.

## Related cookbooks

- `20-Classify-RAG-Passages.md` — the upstream pipeline stage that assembles the evidence this pattern later verifies.
- `31-Universal-Verification-Layer.md` — the general verification-layer pattern this citation checker is one instance of.
- `23-Structured-Extraction-Cascade.md` — another two-stage cheap-then-verify pipeline, verifying extracted fields instead of citations.
</content>
