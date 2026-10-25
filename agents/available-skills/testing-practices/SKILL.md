---
name: testing-practices
description: >
  Use when writing or expanding tests, or fixing a bug — how we write tests
  here and the mandatory characterize → falsify → fix protocol. Load when a change
  adds/touches a test or fixes a bug. For Playwright or browser UI e2e
  (specs, page objects, fixtures, playwright.config, flaky browser tests),
  also load world-class-playwright.
---

# Testing Practices

Tests describe **behavior, not implementation** — they must survive an internal
refactor untouched. Every change leaves the suite stronger, proportional to what it
touched. This is enforced, not optional: the class-of-bug is the deliverable, not
just the instance.

A regression test is valuable only if it turns red for the regression it claims
to prevent. Design the failure mode and observable contract before the mechanics.

## Routing

This skill owns unit, API, integration, and language-agnostic test design / bug-fix
protocol. For Playwright and browser UI e2e (specs, page objects, fixtures,
`playwright.config`, flaky browser tests), load `world-class-playwright`. Locators,
fixtures, lint, CI gates, file layout, escape hatches, health gates, and
`@characterization-only` live there — point; do not copy.

## Lowest-cost layer

Choose the lowest-cost layer that can measure the real failure: unit for logic;
API/integration for service contracts; browser UI for critical journeys and
high-risk rendering. Critical paths (quote, sign-up, payment, form submission)
get browser tests. Do not force every edge through a full UI journey.

## Bug-fix protocol (mandatory, test-driven)

A bug fix is not done until the bug is proven dead by a test proven alive first.
New tests: characterize → falsify → fix. Characterization assertions must not
merge. Playwright's marker (`@characterization-only`) lives in
world-class-playwright; other layers keep characterization local and uncommitted.
Do not invent a testing-practices-level marker.

1. **Characterize** — temporarily prove the current buggy behavior is present
   (green against the bug). Guards against writing a test for the wrong symptom.
2. **Falsify** — replace that with the desired contract and **prove it fails for
   the right reason** (the bug, not a typo or missing import). Capture the red
   output.
3. **If you must change an existing test, first prove the original was red** against
   the buggy code: `git stash` → run → capture → `git stash pop`. The change must
   show: original result → why it was insufficient → the new/changed test.
4. **Implement the minimal fix.** Understand _why_ the code was written this way
   before changing it.
5. **Prove green**, then run the full gate (`mise run ci`). Include the red→green
   evidence.
6. **Prevent the class where you can** — a facade/abstraction that makes the misuse
   impossible, a stronger type that makes the bad state unrepresentable, or a
   lint/scan rule that fails the pattern in CI. State what class is now prevented,
   or why it can't be.

## What to add on any change

- The code path you changed must have coverage in this change — even if it had none.
- Adjacent code you newly depend on gets a focused test.
- Test names describe behavior:
  `TestCreateUser_WithDuplicateEmail_ReturnsConflictError`.
- Tickets are traceability metadata, not test architecture. Name tests after
  behavior; record issue IDs as annotations or repository-standard metadata.
- A test has one coherent reason to fail. Several assertions may support the same
  product claim; they must not bundle unrelated claims.

## Boundaries

- Test the code your change touches and its immediate collaborators. A coverage
  safari of unrelated modules is its own ticket.
- Tests are independently runnable from a clean context. Do not share mutable
  page, user, or environment state to amortize setup.
- Wait on signals at every layer (web-first assertions, event-driven waits,
  named readiness). No sleep, `waitForTimeout`, or hand-rolled polling in specs.

## Gotchas

- Never edit a test to pass without first showing it was red — a test that was
  never red proves nothing and hides the bug's return.
- One targeted integration test that exercises real behavior beats five shallow
  unit tests that mock everything away.
