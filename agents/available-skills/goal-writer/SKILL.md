---
name: goal-writer
description: Turn a loose request, conversation context, work order, or existing /goal into one bounded, transcript-verifiable completion condition. Use when the user asks to set, write, rewrite, or turn something into a /goal or done-condition for an autonomous agent loop.
---

# Purpose

Write the smallest completion contract that preserves the user's exact intent and makes premature success difficult.

A goal states what must be true at the end. It does not narrate progress, history, motivation, or implementation steps.

## Workflow

1. Preserve every material requirement, population, quantifier, source-to-destination relationship, constraint, and explicit verification method from the request or conversation.
2. Express the desired end state first. Prefer one decisive completion state; represent additional requirements as constraints or separate zero-gap invariants when they apply to distinct populations.
3. Remove backstory, current-state framing, rationale, filler, hedges, false starts, and speculative implementation details.
4. Make each completion clause provable from evidence surfaced in the transcript. Prefer concrete test/build results, exit codes, counts, empty result sets, diffs, mappings, browser observations, or other observable verification appropriate to the task.
5. Do not rely on sampling when the request says all or every. Artifact existence alone is not proof of correctness.
6. Keep implementation freedom unless the user requires a method. Do not invent tools, paths, commands, populations, restrictions, or agent topology.
7. End with a bound: use the user's turn/time bound when supplied; otherwise use `or stop after 20 turns` unless the scope clearly requires a different conservative bound.

## Decision rules

- Treat scope preservation as higher priority than brevity. Never broaden, narrow, merge, or substitute distinct populations.
- Preserve meaningful `all`, `every`, `any`, `at least one`, `may`, `must`, and `must not` exactly in effect.
- Do not introduce narrowing words such as `mapped`, `relevant`, `applicable`, or `in-scope` unless the user defined that scope or the meaning is unambiguous.
- When multiple artifact types are related, preserve each relationship independently, such as source -> issue and issue -> test -> verification result.
- When tests are required, require behavioral assertions or outcomes, not merely a test file or association. Preserve stronger existing coverage and never weaken correctness to obtain a pass.
- When the evaluator cannot inspect the environment directly, require decisive evidence to appear in the transcript or final result.
- A blocker is not success. If an external dependency prevents completion and the user asked for blocker handling, require the unmet condition and concrete blocker to be reported.

## Output

Return exactly one line and nothing else.

By default, return only the completion condition. If the input already begins with `/goal` or the user explicitly asks for paste-ready `/goal` syntax, return `/goal` followed by the condition on the same line.

Keep the line within 4,000 characters.
