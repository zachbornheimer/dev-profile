# world-class-playwright

A Playwright engineering skill for producing deterministic, falsifiable,
maintainable, diagnosable browser tests and operating the suite as a platform.

## Core standard

The skill now treats **test correctness** as more than "the spec is green": a
regression test must have a clear product claim, a concrete failure mode, and an
assertion that cannot silently pass because the wrong element/state/value was
observed.

This is especially important for large generated test batches. Ticket coverage
is not test quality; generated tests receive a separate falsifiability and
false-positive audit.

## Included

```text
SKILL.md
references/
  architecture.md
  dynamic-wizards.md
  enforcement.md
  golden-paths.md
  performance.md
  review.md
  stability.md
  test-design.md
assets/
  ci/playwright.example.yml
  eslint.config.example.mjs
  fixtures/base.example.ts
  scripts/new-spec.example.mjs
  scripts/reject-characterization-tests.example.mjs
  timeouts.example.ts
```

## High-value rules

- Organize tests around product behavior; keep issue IDs as traceability metadata.
- Each test has one coherent product claim and a known failure path.
- For defect fixes, prefer characterize → falsify → fix: green on the observed defect, red on the desired contract, then green after the fix.
- Temporary characterization assertions are explicitly marked and mechanically rejected by CI so an interruption cannot turn known-wrong behavior into an apparently valid contract.
- Required state is asserted, never conditionalized away.
- Prefer strict user-facing locators and scoped exact outcomes.
- Do not use `.first()` or broad text/value heuristics to make ambiguity disappear.
- Tests are isolated; serial/shared-page suites require a real external constraint.
- Use API/deep-link/setup fixtures for prerequisites that are not under test.
- Use component, visual, geometry, or full-browser tests according to the actual risk.
- For transient states, control entry/duration before asserting behavior.
- Review generated batches for repeated conceptual mistakes and sample deliberate
  failures across each recurring pattern.

## Before adopting

Verify `eslint-plugin-playwright` rule names against the version installed by the
target repository. Treat the included assets as starting points: adapt fixture,
API, timeout, and CI policy to the product rather than copying them blindly.

For an existing suite, ratchet new rules in rather than making legacy debt
unmergeable in one change. See `references/enforcement.md`.

## Architecture first

For generated or bulk-written tests, map requirements to product behaviors and
owning surfaces before generating code. Tickets remain traceability metadata. A
green batch is not accepted until tests are independently runnable, structurally
owned, and demonstrably capable of failing for the intended regressions.
