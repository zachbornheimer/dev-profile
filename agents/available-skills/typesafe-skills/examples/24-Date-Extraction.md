---
name: 24 Date Extraction
description: Use TypeSafe Choice questions to identify which parts a date expression states — absolute, relative, or absent — then resolve calendar math, validation, and review routing deterministically in code.
---

ORIGINAL SOURCE: <https://docs.typesafe.ai/cookbooks/date_extraction_cookbook>
VIDEO: none
Use the original source primarily. This skill below is a summary in our own words. View details at this link.

## When to use

Extracting a date referenced in text (a deadline, an effective date, an anchor like "next Thursday") where the model should read what the text states but never perform calendar arithmetic itself.

## What it demonstrates

The cookbook implements `extract_date(document: str, role: str) -> dict`, which takes a document and a phrase naming the desired date (e.g. "the deadline to return the form") and returns the resolved date, a confidence score, a review flag, and an explanatory note. One API call answers seven `Choice` questions: `mode` (absolute / relative / none), `month`/`day`/`year` (for absolute dates, year range 1900-2050), `day_anchor` (today, tomorrow, day_after, weekday — for relative dates), `weekday`, and `week_offset`.

## Steps / call shape

```text
document -> typed date parts (7 Choice questions, 1 call) -> deterministic resolver -> valid date / review
```

Code resolves the typed parts into a concrete `date` object — the model never calculates "next Thursday" or validates February 30. Confidence for the whole extraction equals the minimum confidence among its constituent parts; results below `REVIEW_BELOW = 0.60` route to human review. Install: `pip install ipython 'cooksafe>=0.2.0,<0.3.0'`. Requires `TYPESAFE_API_KEY`. Model: `jev-1.12`.

## Results / numbers

From four test documents:

| Case                            | Confidence | Outcome            |
| ------------------------------- | ---------- | ------------------ |
| Contract date, year stated      | 0.97       | resolved           |
| Contract date, year stated      | 0.91       | resolved           |
| Form deadline, year inferred    | 0.95       | resolved           |
| Relative date ("today")         | 0.94       | resolved           |
| Relative date ("next Thursday") | 0.92       | resolved           |
| Non-existent date               | 0.46       | flagged for review |

## Pitfalls

- Year inference: when no year is stated, code uses the current year, advancing to next year only when the resolved date would be more than 31 days in the past — don't let the model guess the year itself.
- Out-of-range years (outside 1900-2050) trigger review rather than a guess; impossible dates (February 30) are caught and flagged, not silently coerced to a nearby valid date.
- Weekday resolution follows explicit conventions: a bare weekday resolves to its next occurrence on or after today; "current" means this week; "next" means the following calendar week — encode these as code rules, not model judgment.
- Route anything below `REVIEW_BELOW` (0.60 in the cookbook) to human review, especially when the date drives a deadline or has financial consequences — don't ship a plausible-looking guess.
- Include an explicit "none"/unstated escape option in the `mode` question rather than forcing the model toward a plausible-but-wrong absolute or relative reading.

## Related cookbooks

- `25-Pre-Parsed-Value-Extraction.md` — the general pattern of typed-part extraction plus deterministic resolution that this cookbook specializes for dates.
- `23-Structured-Extraction-Cascade.md` — verifying extracted structured fields, applicable if date extraction feeds a larger record.
- `26-Hierarchical-Classification.md` — another pattern that decomposes one judgment into several typed sub-questions resolved together.
  </content>
