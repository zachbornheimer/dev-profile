---
name: 25 Pre-Parsed Value Extraction
description: Over-find candidate values with regex, use Choice to select the one the question asks for, then normalize the exact chosen span in code so the model can never invent or transpose a digit.
---

ORIGINAL SOURCE: <https://docs.typesafe.ai/cookbooks/pre_parsed_value_extraction_cookbook>
VIDEO: none
Use the original source primarily. This skill below is a summary in our own words. View details at this link.

## When to use

A regex or parser can reliably find every candidate span of a value type (emails, phone numbers, money amounts) but cannot tell which candidate the question is actually asking for. Use this whenever the extraction problem splits into "where might it be" (easy, deterministic) and "which one is meant" (hard, semantic).

## What it demonstrates

The cookbook runs the pattern across three value types: email addresses (which address is the sender's, which is the requested receipt address), phone numbers (which of several numbers is the direct mobile line, normalized to E.164 with `phonenumbers`), and money amounts (which amount is the total due, and whether a given amount is a charge or a credit). In every case, a recall-tuned regex over-finds candidates, and a TypeSafe `Choice` picks the one that answers the question — restricted to the literal candidate strings the regex found, plus a `none` option.

## Steps / call shape

```text
raw text
  -> deterministic candidate finder (recall-tuned regex)
  -> TypeSafe Choice among exact candidates + none
  -> deterministic normalization/validation
```

```python
def find(pattern: re.Pattern, text: str) -> list[str]:
    """Code-side candidate finder: recall-tuned regex, deduped, in document order."""
    seen: set[str] = set()
    out: list[str] = []
    for match in pattern.findall(text):
        span = match.strip()
        if span and span not in seen:
            seen.add(span)
            out.append(span)
    return out


candidates = find(EMAIL_RE, EMAIL_DOC)
answer = Choice(
    instructions="Which candidate is the invoice total?",
    criteria={**{c: None for c in candidates}, "none": "No candidate fits"},
)
```

For the phone number case, the selected candidate is parsed and normalized only after TypeSafe picks it:

```python
mobile = pick(PHONE_DOC, phones, "Which of these is the direct mobile / cell number?")
region = classify(
    PHONE_DOC,
    "In what country is this office located?",
    ["US", "GB", "DE", "FR", "CA", "AU"],
)
parsed = phonenumbers.parse(mobile["choice"], region["choice"])
e164 = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
```

Because the `Choice` can only return one of the regex-found spans, the returned value is copied unchanged — it cannot invent a value or transpose a digit.

## Results / numbers

- Email: sender's requested receipt address identified at confidence 0.98; the From-line sender at confidence 1.00.
- Phone: mobile candidate resolved and normalized to `+14155550177`.
- Money: `$1,315.50` classified as a charge (P(credit) = 0.01); `$50.00` classified as a credit (P(credit) = 0.99).

## Pitfalls

- `Choice` supports at most 255 options — for candidate sets larger than that, filter in two stages rather than passing every candidate at once.
- Candidate discovery is domain-specific: emails and phone numbers have reliable regexes, but names need an external roster, NER, or LLM-proposed candidates instead.
- Decimal-format assumptions are locale-dependent (US comma-thousands/period-decimal vs. European reversed) — ask a `Noul` question for which convention the document uses and branch on it in code rather than hardcoding one format.

## Related cookbooks

- `24-Date-Extraction.md` — the same over-find-then-select pattern applied to dates instead of values.
- `30-Hybrid-Parsing-and-Semantic-Selection.md` — the generalized version of this pattern across value types, dates, and other candidate-generation problems.
