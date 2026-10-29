---
name: 30 Hybrid Parsing and Semantic Selection
description: Keep regexes, parsers, indexes, and databases for candidate generation, and use TypeSafe only for the step that requires meaning to select, match, or interpret among those candidates.
---

ORIGINAL SOURCES:

- <https://docs.typesafe.ai/cookbooks/pre_parsed_value_extraction_cookbook>
- <https://docs.typesafe.ai/cookbooks/date_extraction_cookbook>
- <https://docs.typesafe.ai/concepts/how-to-build-with-system-one>

This is a cross-cutting pattern with no single source page; it draws on the three pages above.
VIDEO: none
Use the original source primarily. This skill below is a summary in our own words. View details at this link.

## When to use

Deterministic code is good at finding _where_ candidates are but bad at knowing _what the user means_. Use this whenever you're tempted to replace a working parser or index with a model — replace only the selection step instead.

## What it demonstrates

`pre_parsed_value_extraction_cookbook` finds emails, phone numbers, and money amounts with recall-tuned regex, then uses `Choice` to select the one candidate that answers the question (see `25-Pre-Parsed-Value-Extraction.md` for the full worked example). `date_extraction_cookbook` takes the same shape further: instead of one `Choice` over whole date strings, it asks seven typed `Choice` questions that read a date's components (mode, month, day, year, day-anchor, weekday, week-offset), then resolves those typed parts to a concrete calendar date in code, including relative dates like "next Thursday." `how-to-build-with-system-one` supplies the underlying reasoning: keep candidate generation and side effects in code, and use narrow typed questions only where interpretation is required.

## Steps / call shape

```text
raw input
  -> deterministic candidate generation
  -> TypeSafe semantic selection/judgment
  -> exact deterministic copy/normalization/action
```

```python
def date_questions(role: str) -> dict[str, Choice]:
    """Seven typed choices that read a date's shape and parts."""
    return {
        "mode": Choice(
            instructions=...,
            criteria={"absolute": None, "relative": None, "none": None},
        ),
        "month": Choice(...),
        "day": Choice(...),
        "year": Choice(...),
        "day_anchor": Choice(...),
        "weekday": Choice(...),
        "week_offset": Choice(...),
    }


def extract_date(document: str, role: str) -> dict:
    return assemble(
        read_parts(document, role)
    )  # assemble() resolves typed parts to a concrete date + confidence
```

Other examples from the pattern: regex finds all emails, TypeSafe decides which is the billing contact; a parser finds all dates, TypeSafe decides which is the renewal date; an AST finds all candidate symbols, TypeSafe judges which violates a semantic convention; a database returns nearby product names, TypeSafe decides which record the user's phrase refers to; BM25/vector search finds candidates, TypeSafe judges relevance.

## Results / numbers

Date extraction cookbook, four documents, auto-accept threshold 0.60 confidence, reference date 2026-07-30:

| Question                 | Expected   | Got        | Confidence | Status         |
| ------------------------ | ---------- | ---------- | ---------- | -------------- |
| Agreement effective date | 2025-01-01 | 2025-01-01 | 0.97       | accepted       |
| Agreement expiration     | 2027-12-31 | 2027-12-31 | 0.91       | accepted       |
| Form return deadline     | 2026-08-14 | 2026-08-14 | 0.95       | accepted       |
| Kickoff call date        | none       | none       | 0.46       | sent to review |
| Survey closing date      | 2026-07-30 | 2026-07-30 | 0.94       | accepted       |
| Design review date       | 2026-08-06 | 2026-08-06 | 0.92       | accepted       |

5 dates auto-accepted, 1 sent to human review.

## Pitfalls

- Do not replace reliable deterministic extraction wholesale — it's still doing the recall/candidate-generation work; the model only ever selects among what it found.
- `Choice` supports at most 255 options; break larger candidate sets into two selection stages.
- Locale and format assumptions (decimal separators, date orderings) must themselves be resolved with a typed question and branched on in code, not hardcoded.

## Related cookbooks

- `25-Pre-Parsed-Value-Extraction.md` — the value-extraction half of this pattern in full detail.
- `24-Date-Extraction.md` — the date-extraction half of this pattern in full detail.
