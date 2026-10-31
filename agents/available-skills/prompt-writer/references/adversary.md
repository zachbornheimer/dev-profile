# Adversary brief

Send this to a reviewer that did **not** author the spec or order. Do not tell it
to "improve the prompt." It finds ways the compiled task could produce a result
the user would reject.

## Inputs

- original user request (verbatim)
- internal intent spec
- compiled work order
- only the extra context needed to assess them (not the author's rationale)

## Attack angles

Report specific defects and a suggested correction per finding. Skip stylistic
preference. Do not rewrite the whole order.

1. **Intent loss** — synthesis omitted or distorted something they care about.
2. **Invented intent** — a guess or implementation suggestion became a requirement.
3. **Missing context** — execution is missing information already available.
4. **Stale assumptions** — facts that should have been researched or inspected.
5. **Ambiguity** — two reasonable agents could read an important requirement
   differently.
6. **Proxy gaming** — the stated done-when can pass without satisfying the goal.
7. **Overconstraint** — the order prescribes implementation and blocks a better
   path.
8. **Underconstraint** — an invariant or blast-radius is missing.
9. **Scope creep** — the worker could expand into adjacent unrequested work.
10. **Duplication** — the order repeats host behavior, project instructions, or
    other skills already in force.
11. **Verification weakness** — a plausible but incorrect result would pass.
12. **Execution risk** — irreversible, destructive, expensive, or externally
    visible action without approval.

## Output shape

```text
Verdict: PASS | REVISE
Findings:
- [angle] defect — suggested correction
Rejected-as-style: (optional) findings you are not asking to change
```

A PASS with no findings is allowed. A rewrite-the-prompt-from-scratch is not,
unless the spec itself is the wrong task.
