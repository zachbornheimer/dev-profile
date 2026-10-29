---
name: 06 Speculative Fan Out
description: Send a classifier and every branch's follow-up questions in one parallel call before knowing which branch will be taken, and let code discard the answers it doesn't need.
---

ORIGINAL SOURCE: <https://docs.typesafe.ai/patterns/fan-out>
VIDEO: none
Use the original source primarily. This skill below is a summary in our own words. View details at this link.

## When to use

A decision tree has several branches and each branch needs its own semantic judgments over the same state — the naive design would classify first, wait, then ask a branch-specific follow-up.

## What it demonstrates

"All questions are evaluated in parallel, so adding more questions usually has little effect on response time." The pattern page walks a support-ticket triage system that asks five questions in a single call instead of sequentially: `category` (Choice: bug_report, billing, feature_request, account), `bug_severity` (Score: cosmetic to blocking), `has_reproducible_steps` (Noul), `refund_requested` (Noul), and `frustration` (Score: calm to very angry). Routing code then reads only the answers relevant to the category that actually won — bug reports with high severity and reproducible steps escalate to engineering, billing tickets with refund indicators route with a flag, feature requests log for developer review, and high frustration scores raise priority across every category regardless of branch.

## Steps / call shape

```python
questions = {
    "category": Choice(
        instructions="Which category best fits `ticket.message`?",
        criteria={
            "bug_report": "...",
            "billing": "...",
            "feature_request": "...",
            "account": "...",
        },
    ),
    "bug_severity": Score(...),  # speculative — only used if category == bug_report
    "has_repro": Noul(...),  # speculative
    "refund_requested": Noul(...),  # speculative — only used if category == billing
    "frustration": Score(...),  # used across every branch
}

response = client.system_one(state=state, questions=questions)
category = response.answers["category"].choice
# code reads only the fields relevant to `category`
```

## Results / numbers

The pattern page itself reports no cost/latency table; the measured cost and speed advantage of sending independent questions in one call — 12.2x cheaper, 10.0x faster on a 13-question batch — is documented in `13-Question-Parallel-Set.md`, which demonstrates the same "ask together" mechanism this pattern relies on.

## Pitfalls

- Speculative questions must still be well-defined against the state already supplied — don't make one question depend on another question's hidden answer within the same call.
- If a later question truly needs newly constructed state (e.g. state built from an earlier answer), that's a second request, not more speculative fan-out — see `13-Question-Parallel-Set.md`'s pitfall on true dependency chains.
- Optimizing for the fewest questions sent can create unnecessary round trips; with state already shared, a few extra narrow speculative questions is often the cheaper architecture than a second call.

## Related cookbooks

- `10-Smart-Home-Assistant.md` — this exact pattern used in an interactive application.
- `13-Question-Parallel-Set.md` — measured cost/latency proof for batching independent questions.
- `09-Intent-Routing.md` — routing on the classifier answer once branch-specific data has already arrived.
