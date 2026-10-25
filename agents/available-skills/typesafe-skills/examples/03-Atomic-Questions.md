---
name: 03 Atomic Questions
description: Decompose one broad judgment into several narrow, independently inspectable questions instead of asking for a single opaque verdict.
---

ORIGINAL SOURCE: https://docs.typesafe.ai/concepts/how-to-build-with-system-one
VIDEO: none
Use the original source primarily. This skill below is a summary in our own words. View details at this link.

## When to use

Whenever a draft question tries to balance several independent factors in one instruction ("is this applicant a strong hire?", "is this spam?") instead of exposing each factor separately.

## What it demonstrates

The build guide frames System One as code-owned and code-controlled: "code handles deterministic work and owns the control flow. The model appears only where the system needs programmable common sense or needs to interpret unstructured data." Its seven-step design workflow is: keep deterministic logic in code, decompose input into a focused `state`, use structured formats for state and questions, ask atomic questions, ask many questions together for parallel evaluation, compose outputs in code with explicit rules or weights, and route on uncertainty rather than guessing. The spam example shows the decomposition directly — instead of "is `message` spam?", ask "does the message request login credentials?", "does sender identity conflict with email domain?", "does it claim an unexpected reward?", "does the link text conceal its destination?" — each independently inspectable and tunable.

## Steps / call shape

```text
"Is this applicant a strong engineering hire?"          # avoid

- How deep is the relevant technical experience shown in `resume`?
- Does `resume` show evidence of system-design experience?
- Does `resume` show evidence of leading a team?
- How closely does the domain experience in `resume` match `role.required_domain`?
```

Write each as a full natural-language question with backticked state paths, not a terse label — TypeSafe answers the question asked, and a label leaves it guessing which judgment is wanted. Combine the answers in code with weights or rules the team can review (see `08-Composite-Scoring.md`).

## Results / numbers

This is a design-pattern page; it publishes no cost or latency numbers of its own. The measured payoff of asking questions together (rather than serially) is documented in `13-Question-Parallel-Set.md`.

## Pitfalls

- Decomposition does not mean serial API calls — ask independent questions together in one request; only issue a second request when a later question's state or options genuinely depend on an earlier answer.
- A terse label instead of a full question leaves the model guessing what judgment is wanted.
- Review checklist before shipping a question: does it ask one thing; is it a full natural-language question pointing at state with backticked paths; could a knowledgeable person answer it quickly given the state; are deterministic subproblems handled in code instead; are criteria concrete enough to distinguish nearby outcomes; can downstream code act on the value directly.

## Related cookbooks

- `02-State-Design.md` — the state these atomic questions point into.
- `08-Composite-Scoring.md` — combining several atomic Score questions into one weighted result in code.
- `13-Question-Parallel-Set.md` — proof that batching atomic questions changes cost and speed, not answers.
