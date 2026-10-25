# Review, Portfolio, and Definition of Done

## Test portfolio

Use the lowest-cost layer that can reliably prove the behavior — moving a check down a layer is usually a 10–100× cost reduction with no loss of confidence:

1. Unit tests for pure logic.
2. Component tests for isolated visual and interaction behavior.
3. API/integration tests for service contracts and business rules.
4. Playwright UI tests for critical user journeys, browser integration, and high-risk rendering behavior.
5. A small number of broad end-to-end smoke tests.

Do not force every edge case through a complete UI journey; a validation rule with eight cases belongs in one API/unit suite plus one UI test proving the message renders.

Tag by purpose (`@smoke`, `@critical`, `@regression`, `@cross-browser`, `@integration-real`, `@visual`, `@a11y`) to support an intentional CI matrix — not as an ungoverned taxonomy. Prune: remove obsolete tests and fix or delete long-quarantined ones; a suite full of ignored red is worse than a smaller trusted one.

## Review checklist

### Intent and falsifiability

- [ ] The test names the product behavior, not the ticket or implementation mechanics.
- [ ] A reviewer can state the concrete regression that should make it fail.
- [ ] Required preconditions are positively asserted; no missing state can silently skip the contract.
- [ ] For a defect fix, characterize → falsify → fix was completed when practical: known-bad behavior was observed, the permanent contract failed on that behavior, then passed after the fix.
- [ ] No executable `@characterization-only` marker remains; CI rejects temporary characterization assertions if work is interrupted.
- [ ] Issue IDs are traceability metadata rather than the primary test organization.

### Architecture

- [ ] Files and `describe` blocks follow product capabilities/surfaces, not ticket
      ranges, PRs, or generation batches.
- [ ] A batch-level scenario map existed (explicitly or mentally) before broad
      generation: duplicate claims merged, unrelated criteria split, and each
      scenario assigned a layer and owner.
- [ ] The spec describes business behavior; a non-author can tell what product claim it proves.
- [ ] Fixtures manage lifecycle rather than hiding scenario steps.
- [ ] Page objects represent cohesive surfaces; components own reusable regions scoped to a root; workflows coordinate pages without owning locators; API clients handle setup and server verification.
- [ ] No god object spans unrelated pages and responsibilities.

### Determinism

- [ ] Independent and order-agnostic; data unique or worker-partitioned; no shared mutable browser or server state.
- [ ] No arbitrary sleeps; time-dependent behavior uses `page.clock`.
- [ ] Every async Playwright call awaited (`no-floating-promises` clean).
- [ ] No force clicks without a documented product reason; no retry loops around user actions; no swallowed errors.

### Locators and assertions

- [ ] Semantic or stable test contracts; every action target unique.
- [ ] `.first()` / `.last()` / `.nth()` justified by product semantics, not used to silence strictness.
- [ ] Repeated components scoped to a root; no styling classes or framework internals as contracts unless intentionally load-bearing.
- [ ] Assertions are scoped to the owning surface; no body-wide text heuristics when a direct contract exists.
- [ ] Regexes, fallback formats, and normalization represent intentional accepted variation rather than making a weak assertion pass.
- [ ] Fixed inputs/configuration lead to one expected outcome; `A or B` assertions are used only for intentionally variable contracts.
- [ ] Numeric/layout assertions directly encode the requirement rather than an arbitrary proxy threshold.
- [ ] Visual/layout regressions use screenshot, component, or geometry assertions when those measure the real failure better than a broad E2E proxy.

### Performance

- [ ] Setup avoids unnecessary UI work (API data setup, stored auth, deep links).
- [ ] Runs fully parallel; expensive worker fixtures measured and safely isolated.
- [ ] No manual browser/context creation duplicating fixtures.
- [ ] CI projects match actual browser risk; slow tests and fixtures observable in reporting.

### Diagnosis

- [ ] Assertions verify observable outcomes; business-level `test.step`s make the failure location obvious.
- [ ] Failures preserve original causes; trace available on CI retry.
- [ ] Artifacts expose no secrets; unknown wizard states fail with visible context.

### Generated/bulk changes

- [ ] Ticket batches were clustered into distinct behaviors and appropriate layers before code generation.
- [ ] Generated tests were audited for repeated false-positive patterns rather than reviewed only file-by-file.
- [ ] Shared journeys/selectors have one intentional owner; generation did not clone them across specs.
- [ ] Deliberate-failure sampling covers each recurring generated pattern.
- [ ] For generated defect fixes, characterization markers are temporary and mechanically blocked from merge rather than trusted to human cleanup.

### Maintainability

- [ ] No generic unknown-field autofill; no universal `clickIfPresent` / `fillIfPresent` hiding required behavior.
- [ ] Types express domain outcomes; comments explain constraints; workarounds link to a defect or removal condition.
- [ ] New abstractions have a clear owner and more than accidental reuse.

## Rejection criteria

Request changes when code contains any of the following without a narrowly documented exception. Each is listed with the failure it causes, because reviewers who can articulate the "why" hold the line under deadline pressure:

- A test whose required assertions are inside `if`, `.count()`, `isVisible()`, or catch-and-continue branches — missing product state becomes a pass.
- Ticket-shaped tests that combine unrelated acceptance criteria — failures are hard to localize and coverage boundaries drift with project management.
- `waitForTimeout` as ordinary synchronization — loses the timing bet on slow runners, wastes time on fast ones.
- Empty catches or ignored Playwright failures — converts diagnosable failures into mysteries.
- Generic input autofill / unknown screens treated as optional — goes green over product contract changes.
- Broad selectors followed by `.first()` or `.or(...).first()` — asserts against whichever element happened to come first instead of defining the contract.
- Cross-test dependencies or tests made serial to share a long-lived `Page`, amortize a journey, or hide collisions — disables isolation, sharding, selective reruns, and reproducible failures.
- Ticket-range/spec-dump files that combine unrelated product surfaces — work-tracking structure has leaked into executable architecture.
- Duplicated multi-page traversal across specs instead of one named workflow, or one workflow/page object that spans unrelated product areas — both create high change fan-out.
- Mutable accounts shared across parallel workers — nondeterministic server-state collisions.
- One fixture performing an entire business scenario / one page object spanning the application — every consumer inherits invisible assumptions.
- Retry-until-success interaction loops — masks product races the suite exists to catch.
- Force clicks bypassing actionability — skips the visible/stable/receives-events checks that make the click meaningful.
- Global timeout increases as the primary fix — slows every test to hide one broken signal.
- Assertions on body-wide text or permissive normalization when a scoped exact contract exists — passes when the right-looking value appears for the wrong reason.
- Deterministic scenarios that accept several unrelated outcomes (`approved|declined|error`) — hides uncontrolled setup or integration behavior.
- Layout requirements replaced by arbitrary proxy thresholds — a test can pass while the visible defect remains.
- A temporary characterization assertion without a CI-rejected marker — intentionally wrong behavior can be mistaken for the permanent contract after interruption.
- A committed `@characterization-only` marker — the branch still contains a test whose green state proves the defect, not the desired product behavior.
- Sensitive data attached to reports.

## Definition of done

A Playwright change is complete only when:

- The test proves the intended observable behavior and its intended regression has a known failure path; for defect fixes, characterize → falsify → fix was completed when practical.
- No temporary characterization marker remains in executable tests, and CI enforces that invariant.
- It passes independently, repeatedly (`--repeat-each`), in parallel, and in a sharded suite.
- Setup uses the cheapest reliable interface; locators are strict and stable; no arbitrary waits or swallowed errors.
- Fixtures, page objects, components, and workflows have clear ownership.
- CI failures are diagnosable from retained artifacts, which contain no secrets.
- Performance impact is measured when the change materially affects suite execution.
- The code is typed, formatted, linted, and maintainable by someone who did not author it.
