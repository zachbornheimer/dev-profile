---
name: world-class-playwright
description: >
  Design, implement, review, refactor, and debug Playwright test suites, and
  operate them as a platform: guardrails, fixtures, timeout policy, CI gates,
  and escape-hatch governance. Use when the task involves Playwright or browser
  end-to-end/UI testing in any form: writing or editing .spec.ts files, page
  objects, component objects, fixtures, or playwright.config; reviewing test
  code in a PR; fixing flaky, slow, or intermittently failing tests; CI
  parallelism, sharding, or retry strategy; test data setup; locator/selector
  questions; standing up a new suite or hardening an existing one; or "why does
  this test time out?" — even when the user says "e2e tests", "browser tests",
  "UI tests", or "automation" without naming Playwright.
---

# World-Class Playwright Engineering

## Mission

Produce Playwright suites that are **deterministic**, **fast**, **maintainable**,
**readable**, **diagnosable**, and **trustworthy**.

Optimize in this order:

> Correctness → determinism → diagnosability → maintainability → execution speed.

With one amendment: **past a latency threshold, speed becomes a correctness
property.** A suite slow enough to be moved off the pre-merge path stops
preventing defects, no matter how correct each test is. Treat p95 wall-clock as
a budget with a hard gate (see Health gates), not as the thing you sacrifice
first.

Never trade correctness or useful failure information for superficial speed. A
fast suite nobody trusts is worthless; teams start ignoring red builds, and the
suite's reason for existing evaporates.

## The governing principle

> A world-class suite does not depend on every contributor making expert
> decisions repeatedly. It encodes expert decisions into fixtures, APIs, types,
> lint rules, CI gates, and narrowly controlled escape hatches.

> A regression test is valuable only if it turns red for the regression it claims
> to prevent. Design the failure mode and observable contract before writing the
> mechanics. Green is evidence only after false-positive paths have been removed.

Corollary, and the main thing that distinguishes this skill from a style guide:
**a rule that exists only in prose is optional.** Every rule below names its
enforcement mechanism. When adding a rule, add its mechanism in the same change,
or mark it explicitly unenforceable so everyone knows where trust is required.

## How to use this skill

Core rules below apply to every Playwright task. Then read the matching file:

| Task                                                                                                                                                                                 | Read                            |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------- |
| Writing/refactoring specs, fixtures, page objects, components, workflows, API clients, builders                                                                                      | `references/architecture.md`    |
| Designing regression tests, turning tickets into scenarios, reviewing generated/bulk test changes, avoiding false positives                                                          | `references/test-design.md`     |
| Standing up guardrails, lint rules, CI gates, escape-hatch policy, adopting this in a legacy suite                                                                                   | `references/enforcement.md`     |
| A recurring situation: popups, downloads, uploads, auth, feature flags, dynamic tables, virtualized lists, eventual consistency, third-party widgets, clock control, background jobs | `references/golden-paths.md`    |
| Slow suite, parallelism, sharding, auth reuse, mocking strategy, playwright.config                                                                                                   | `references/performance.md`     |
| Multi-step wizards, variable page sequences, dynamic flows                                                                                                                           | `references/dynamic-wizards.md` |
| Flaky test, intermittent failure, timeout debugging, diagnostics setup                                                                                                               | `references/stability.md`       |
| Reviewing a PR, auditing a suite, judging "is this done?"                                                                                                                            | `references/review.md`          |

Example starting points live in `assets/`: `eslint.config.example.mjs`,
`timeouts.example.ts`, `fixtures/base.example.ts`, `ci/playwright.example.yml`, `scripts/new-spec.example.mjs`.
Copy and adapt these rather than describing them.

Before writing code in an existing repository, read that repo's
`playwright.config`, fixtures, page objects, and naming conventions. Reuse
existing abstractions when ownership matches rather than inventing parallel ones.

---

## Non-negotiable rules

Each rule names the failure mode it prevents — so you can recognize it, and
reason correctly about novel situations the rules don't anticipate — and the
mechanism that enforces it.

### Test architecture and decomposition

- Design the suite around **product capabilities and surfaces**, not tickets, PRs,
  defect batches, or the order work happened to arrive. A work item is metadata;
  it is not a file boundary, `describe` boundary, or scenario boundary.
- Before generating or editing many tests, build a scenario map: for each distinct
  product claim record the owning surface, appropriate test layer, setup path,
  observable outcome, and traceability IDs. Merge duplicate claims and split
  unrelated claims before writing code.
- Spec files own cohesive behavior for one product area. Specs state intent and
  outcomes; page/component objects own locator mechanics; workflows own reusable
  multi-surface journeys; fixtures own lifecycle/isolation; API clients own cheap
  setup and server verification. Do not blur these boundaries to save a few lines.
- A test should be runnable by itself from a clean context. Do not amortize an
  expensive journey by sharing a mutable `Page` or serial state across several
  tests. Reach the deep state through an API, fixture, deep link, or reusable
  workflow instead.
- If several assertions truly describe one irreversible journey and isolated setup
  is not practical, make it **one scenario** with meaningful `test.step`s rather
  than several tests that secretly depend on one another.
- Keep broad end-to-end journeys small in number. Use focused tests at the lowest
  reliable layer for individual validation, visual, layout, component, and service
  contracts. Do not turn one browser journey into the repository's catch-all test.
- Repeated selectors belong in an owning page/component object; repeated business
  navigation belongs in a workflow. Do not create universal helpers or god page
  objects that span unrelated surfaces.
- Abstractions must reduce change fan-out. If a routine UI refactor requires edits
  across many specs, selector ownership is wrong. If one scenario change requires
  changes across unrelated abstractions, orchestration ownership is wrong.

_Enforced by:_ repository layout/import boundaries, independent-test CI, serial
block linting, review of scenario maps for bulk generation, and the ownership
rules in `references/architecture.md`.

### Test intent and falsifiability

- Start from one product claim: prerequisite state, action, observable outcome,
  and the concrete regression that should make the test fail.
- Tickets are traceability metadata, not test architecture. Do not mechanically
  create one browser test per ticket or combine unrelated acceptance criteria
  because they share an issue ID. Name tests after behavior; record issue IDs as
  annotations or repository-standard metadata.
- A test has one coherent reason to fail. It may assert several facets of that
  outcome, but every assertion must support the same product claim.
- Required preconditions are asserted, never optionalized with `if`, `.count()`,
  `isVisible()`, `clickIfPresent`, or catch-and-continue logic.
- Assertions are scoped to the owning surface and prove the exact outcome. Avoid
  body-wide text scans, broad regexes, permissive normalization, or "one of these
  values somewhere on the page" heuristics unless that variability is itself the
  contract.
- Deterministic scenarios have deterministic expected outcomes. `A or B`,
  fallback locators, and broad result unions usually mean dependencies or
  configuration are uncontrolled; model legitimate variants as explicit separate
  cases.
- Test the requirement, not a convenient proxy: "full width" means relative to
  its container, not an arbitrary pixel minimum; a documented minimum hit target
  can be asserted numerically.
- Prefer user-visible behavior over CSS classes, framework internals, private
  keys, or DOM shape. Implementation details are asserted only when they are an
  intentional contract, and the reason is documented at their abstraction
  boundary.
- Choose the lowest-cost layer that can measure the real failure. Visual/layout
  defects often belong in component, screenshot, or focused geometry tests
  rather than a complete end-to-end journey.
- For defect fixes, prefer a **characterize → falsify → fix** cycle when practical:
  1. **Characterize (green):** temporarily prove the current buggy behavior is
     actually present. This guards against writing a test for the wrong symptom.
  2. **Falsify (red):** replace that temporary assertion with the desired product
     contract and confirm the unchanged buggy implementation fails for the intended
     assertion.
  3. **Fix (green):** change production code and confirm the same contract passes.
- Temporary characterization assertions describe known-wrong behavior and MUST be
  mechanically unmergeable. Mark them with the repository-standard temporary
  marker (the examples use `@characterization-only`) and make CI reject that marker
  in executable tests. Do not rely on a reviewer or interrupted developer to
  remember which green assertion was intentionally backwards.
- If the exact known-bad state cannot be reproduced safely, use the strongest
  available negative control and document what was not mechanically verified.

_Enforced by:_ strict locators, conditional-test lint rules, review checklist,
CI repetition, the temporary-characterization marker guard, and the
design/negative-control workflow in `references/test-design.md`. Semantic
correctness remains partly a review duty.

### Test independence

- Tests are independent, repeatable, order-agnostic, and safe to shard. Anything
  less silently caps parallelism and turns every CI change into Jenga.
- A test asserts one coherent business outcome. A broad journey test may assert
  several outcomes of _that journey_; it may not become a grab bag.
- Tests never depend on another test having run, and never share mutable
  records, users, files, browser state, or environment state unless access is
  partitioned by worker. Identity, tenancy, and data namespaces come from
  fixtures — never constructed inline.
- Serial execution is exceptional, documented, justified by an external or
  product constraint, and never used to share a mutable `Page`, amortize a long
  journey across tests, or hide a state collision. If several assertions require
  one irreversible journey, either create isolated setup for each test or make
  the journey one test with meaningful `test.step`s.
- Retries are diagnostic evidence, not a fix. A test that fails then passes must
  stay visible as flaky in reporting, or the suite quietly accumulates rot until
  trust collapses.

_Enforced by:_ `no-restricted-syntax` (module-level mutable state, literal user
records), fixture-only identity, CI `--fail-on-flaky-tests`, shuffle job.

### Waiting and synchronization

The suite defines a **closed set** of permitted waiting mechanisms. Anything
outside it is a lint failure, not a judgment call.

Permitted:

1. Web-first assertions (`await expect(locator).toBeVisible()` and friends).
2. Event-driven waits for navigation, response, download, popup, worker.
3. Named application readiness signals exposed by the app.
4. Centralized response predicates from the API layer.
5. Domain primitives for eventual consistency — one per concept, owned by the
   domain: `await ordersApi.waitForStatus(orderId, 'confirmed')`. Fifteen
   hand-rolled versions of "wait until the order is ready" is the failure this
   prevents.
6. `page.clock` for time-dependent behavior (expiry, debounce, scheduled UI).

Prohibited: `waitForTimeout`, `setTimeout`, hand-rolled polling loops,
`waitForSelector`, arbitrary locator waits, and `networkidle`. A sleep encodes a
guess about machine speed — simultaneously too slow on a fast machine and too
short on a loaded runner, which is the root cause of a large share of all
flakiness. `networkidle` is not readiness: apps with polling, analytics, or
websockets never go idle, and apps that do go idle may still not be ready.

Bounded waits genuinely are necessary for asserting the _absence_ of a signal.
Confine them to one module in `support/`, exempt that module in lint config, and
let nothing else hand-roll one.

Do not lower timeouts to make the suite look faster. Remove work and wait on
stronger signals.

_Enforced by:_ `playwright/no-wait-for-timeout`, `playwright/no-networkidle`,
`playwright/no-wait-for-selector`, `no-restricted-syntax` for `setTimeout` and
`new Promise` sleeps, path-scoped exemption for the one bounded-wait module.

### Timeouts

Timeouts are policy, set by category, not chosen per test:

```ts
export const timeout = {
  assertion: 5_000,
  navigation: 15_000,
  backendConsistency: 30_000,
  test: 45_000,
} as const
```

A local override requires a reason and a ticket via the escape-hatch syntax.
Without that, slow tests normalize themselves one 200ms at a time.

_Enforced by:_ `no-restricted-syntax` on `test.setTimeout` and numeric literal
timeout arguments; per-test duration budget gate in CI.

### Errors

- Never swallow an unexpected Playwright error: no empty catches, no converting
  an unknown interaction failure into `false`, `null`, or "not present". A
  swallowed error turns a test that _cannot fail_ into a test that _cannot
  protect_.
- Optional UI may be probed explicitly (`isVisible()`, `count()`,
  `isChecked()`); once an element is known to be required, interaction failure
  must throw with business context.
- Preserve the original error as `cause` when adding context.

_Enforced by:_ `no-empty` (catch), `no-restricted-syntax` on inline
`.catch(() => …)`, `playwright/no-conditional-expect`.

### Locators

Preference order — each level is a stronger, more user-meaningful contract:

1. `getByRole` with an accessible name.
2. `getByLabel`.
3. `getByPlaceholder`, `getByText`, or another user-facing contract.
4. `getByTestId` for controls that are ambiguous or not naturally accessible.
5. Short, stable CSS only when no semantic contract exists — inside a page or
   component object, never in a spec.

- Locators must uniquely identify their target. Strict mode is an ally: an
  ambiguity error today is cheaper than a wrong-element click that passes for
  six months.
- No `.first()`, `.last()`, `.nth()` unless position is part of the product
  contract, declared via escape hatch. In particular, `.or(...).first()` is not
  a compatibility strategy; it hides which product contract is expected.
- No long CSS chains, XPath, styling classes, generated IDs, or framework
  internals — they change for reasons unrelated to product behavior, which is
  the definition of a brittle contract.
- No broad selectors (`input[type="tel"]`, `select:visible`,
  `input[name*="address"]`) when multiple fields can match.
- Scope repeated structures to their owning region before locating children.
- Prefer generating a union type of valid test IDs from application source and
  typing `getByTestId` against it. A stale or typo'd ID then fails at compile
  time instead of after a 30-second timeout.
- A control that cannot be located semantically is usually an accessibility
  defect. Escalate missing names, labels, and wrong roles to the product team
  rather than compensating indefinitely with CSS.

_Enforced by:_ `playwright/no-raw-locators`, `playwright/no-nth-methods`,
`no-restricted-syntax` for XPath and `page.locator` with CSS in `specs/`, branded
test-id type.

### Assertions

- Prefer web-first assertions. `expect(await locator.isVisible()).toBe(true)`
  snapshots one instant and races the app.
- Assert the value, not a boolean. `expect(delta).toBeLessThanOrEqual(3)` reports
  the number; `expect(delta <= 3).toBe(true)` reports "expected true, received
  false" and forces every author to hand-write a compensating message.
- Assertions verify observable outcomes, not that a click completed.
- Scope assertions to the owning region. Do not use `body.innerText()` or broad
  page-wide searches when the target surface can be identified directly.
- Exact contracts get exact assertions. Regexes, numeric normalization, fallback
  formats, and `A | B | C` expectations are appropriate only when each allowed
  variation is a documented product behavior.
- For absence, first assert a positive readiness signal so "not found" cannot mean
  "the page was not ready yet."
- `expect.soft` reports several independent facets of one outcome; it never lets
  a broken precondition slide.
- `toMatchAriaSnapshot` when the _structure_ of a region is the contract (menus,
  tables, navigation).
- Standardize recurring business assertions as domain matchers:
  `await expectOrder(orderId).toBeConfirmed()`. A domain matcher encodes one
  question and keeps its diagnostics; it must not become a vague wrapper hiding
  a dozen unrelated checks. Domain matchers are load-bearing — unit-test them.
- Scenario outcomes belong in the spec. Page and component objects assert only
  local invariants and readiness.

_Enforced by:_ `playwright/prefer-web-first-assertions`,
`playwright/expect-expect`, `@typescript-eslint/no-floating-promises` (an
unawaited assertion silently makes a test unable to fail), `no-restricted-syntax`
on `.toBe(true)`.

### Test data

- Create prerequisites through APIs, database-safe utilities, or purpose-built
  hooks when the UI path is not the behavior under test. The fastest UI action is
  the one the test doesn't perform. Setup may not bypass behavior the test
  depends on.
- Use the UI only for the behavior being validated.
- Data is unique wherever parallel collisions are possible, from a fixture, not
  `Date.now()` — which collides across workers in the same millisecond.
- Builders produce valid defaults and allow overrides; tests state which values
  matter so a reader can separate signal from scaffolding.
- Never fill unknown inputs with generic fallback values. A newly required field
  must fail actionably until its intended value is defined; autofill silently
  papers over a product-contract change.
- Cleanup is idempotent, registered through a fixture, and tolerates partially
  completed setup.

_Enforced by:_ `no-restricted-syntax` on literal credentials and fixed record
IDs, fixture-only identity, cleanup-success rate gate.

---

## Mandatory structure

```text
tests/
  specs/          Business scenarios and outcomes
  pages/          Page-level interaction contracts
  components/     Reusable UI region contracts
  workflows/      Reusable multi-page business actions
  fixtures/       Dependency composition and isolation
  api/            Setup, cleanup, and backend assertions
  builders/       Typed test-data construction
  assertions/     Domain-specific matchers
  support/        Diagnostics and infrastructure only
```

Prohibited: `helpers.ts`, `utils.ts`, `common.ts`, and universal page objects.
These are ownership vacuums; everything lands in them and nothing can be changed
safely afterwards.

**The structural rule that makes the rest work:** `@playwright/test` may be
imported only from `fixtures/`. Every spec then necessarily comes through the
base fixture, which becomes the single surface for auth, identity, data
namespaces, clock, API clients, cleanup, and diagnostics. Policy changes become
one edit instead of N.

---

## Escape hatches

Every rule needs a sanctioned, more-annoying legal path, or it gets routed around
invisibly. Ban `waitForTimeout` with no alternative and you get
`await new Promise(r => setTimeout(r, 500))`, which lint won't catch by default.

One syntax, everywhere:

```ts
// playwright-standard-disable-next-line no-positional-locator
// Reason: third-party date widget exposes no semantic identifiers.
// Remove when: VENDOR-1842 is resolved.
const month = calendarCells.nth(monthIndex)
```

Every exception must be local, documented, greppable, linked to a defect or
architectural constraint, and carry a removal condition. Count them; trend them.
A rising count is a signal about the product, not just the suite.

---

## Health gates

Suite-level acceptance criteria, gated in CI, not aspirational:

- Zero unexpected retries across a defined observation window.
- p50 / p95 test duration within budget; per-test budget failing the build.
- Changed specs pass `--repeat-each=5` before merge — flake caught at the point
  of introduction, not six weeks later in a triage backlog.
- Clean run under shuffled order and under sharding.
- Quarantine is bounded: a quarantined test has an owner and an expiry date, and
  the build fails when the date passes.
- Selector-quality compliance (ratio of semantic to test-id to raw locators),
  trended.
- Cleanup success rate.
- Trace available for every CI failure.

**Flakiness triage starts with the application.** The first question on an
intermittent failure is whether the product has a real race condition. Suites
that assume the test is wrong train teams to paper over genuine defects.

---

## Implementation workflow

Before writing code:

1. Read the existing config, fixtures, page objects, API clients, builders,
   existing coverage, and naming conventions.
2. Write the product claim, the regression that should make it fail, and the
   strongest observable assertion that proves it.
3. Choose the lowest-cost test layer that can measure that failure reliably.
4. Identify the cheapest reliable setup path (API? deep link? reused auth state?)
   without bypassing the behavior under test.
5. Identify isolation, parallelism, and transient-state control requirements.
6. Reuse an abstraction only when ownership matches; prefer a small local
   implementation over expanding an unrelated "universal" helper.

While writing:

1. Start with the scenario in the spec — behavior in the title, issue IDs in
   annotations/metadata.
2. Create explicit test data through fixtures and builders.
3. Add only the page/component/workflow methods the scenario requires.
4. Prove required states explicitly; do not branch around missing contracts.
5. Use semantic, strict locators and permitted synchronization only.
6. Assert exact, scoped outcomes; use visual/geometry assertions when rendering
   is the contract instead of substituting a weak DOM proxy.
7. Wrap meaningful phases in `test.step` — the cheapest single improvement to a
   failure trace, and the thing most often missing from otherwise good suites.
8. Let fixtures attach diagnostics automatically.

Before completion:

1. Run formatting, linting, and type checking.
2. For defect fixes, complete characterize → falsify → fix when practical:
   observe the temporary characterization green, the permanent contract red on
   the unchanged defect, and that same contract green after the fix. Confirm the
   red failure is the intended product contract, not setup noise or an unrelated
   locator.
3. Confirm no temporary characterization marker remains in executable tests; CI
   must reject one if an interruption leaves the intentionally-wrong assertion in
   the branch.
4. Run the focused test with `--repeat-each`, then the containing project in
   parallel, on the CI browser/project. `--last-failed` to iterate cheaply.
5. Confirm the test passes independently and under shuffle or sharding.
6. Confirm no secrets in artifacts.

For new or substantially changed infrastructure — fixtures, base page objects,
domain matchers, diagnostics — also inspect a deliberately generated failure
trace. A test you have never seen fail is a test whose diagnostics you have never
verified. This is not required for routine small edits to an existing spec.

---

## Generated and bulk test changes

When creating or reviewing many tests from tickets, prompts, recordings, or code
agents, optimize for distinct product coverage, not test count.

Before generation, cluster requirements by behavior and test layer; identify
existing coverage and shared setup. After generation, audit the entire batch for
repeated conceptual mistakes: ticket-shaped test organization, oversized tests,
ambiguous locators, `.first()`/`.or(...).first()`, body-wide text scans,
implementation-detail assertions, conditional expectations, serial/shared page
state, timeout inflation, duplicated journeys, and permissive matchers.

A generated batch MUST include a falsifiability pass. Sample deliberate failures
across each recurring test pattern because a generator can clone one false
positive hundreds of times. Do not accept "all green" as evidence that the
assertions protect the intended regressions.

See `references/test-design.md` and `references/review.md`.

---

## Diagnostics are infrastructure

Every failure automatically carries test-data identifiers; user, tenant, and
worker identity; relevant URLs; API correlation IDs; feature-flag state; console
errors; failed network requests; screenshot and trace; and sanitized domain
state.

This is attached by fixtures, not by each author remembering. See
`assets/fixtures/base.example.ts`.

---

## Test portfolio

Use the lowest-cost layer that can reliably prove the behavior: unit tests for
pure logic; component tests for isolated interaction; API/integration tests for
service contracts and business rules; Playwright UI tests for critical journeys,
browser integration, and high-risk rendering; visual comparison when pixels or
layout are the contract; a small number of broad smoke tests.

Higher layers cost meaningfully more per check — the common "order of magnitude
per layer" figure is a heuristic, not a measurement, and cheap parallel browser
runs have narrowed the gap. Measure your own ratio rather than inheriting the
number. The durable point stands: don't force every edge case through a complete
UI journey.

Tag by purpose (`@smoke`, `@critical`, `@regression`, `@cross-browser`,
`@visual`, `@a11y`) to support an intentional CI matrix, not an ungoverned
taxonomy.

---

## Code quality

- TypeScript strict mode for new suites. Explicit domain types; `unknown` and
  narrowing rather than `any`.
- Prefer meaningful outcomes over Boolean blindness — but a page object that
  returns "confirmed or declined" and a spec that branches on it usually means
  the test doesn't know what it expects, which is a determinism problem wearing
  a type-safe hat. Reach for a result union against genuinely bimodal external
  systems; otherwise write two tests, each asserting one outcome.
- Separate discovery from required action for optional elements. No
  `clickIfPresent()` as a universal primitive — it hides product-state mistakes.
- Locators `readonly`; methods small and intention-revealing; causes preserved
  when wrapping errors.
- Comments explain constraints and reasons, not syntax. Workarounds link to a
  defect or state a removal condition.
- Remove dead selectors, stale workarounds, commented-out tests.

---

## Adopting this in an existing suite

You will not start greenfield, and flipping forty rules to `error` on a legacy
suite produces one unmergeable pull request that gets abandoned.

1. Land the base fixture and the import restriction first. Everything else
   depends on specs funnelling through one surface.
2. Turn on rules as `warn` with a checked-in baseline count; fail the build only
   when a count increases (Betterer, or a committed baseline file). Ratchet down.
3. Add the spec generator early, so new files start from the blessed shape
   instead of a copied neighbour. Most drift enters by copy-paste, not by
   ignorance.
4. Migrate by risk, not by directory: the flakiest and slowest specs first.
5. Track the escape-hatch count from day one so you can tell migration debt from
   new debt.

## The limits of enforcement

Guardrails raise the floor and stop drift. They do not produce insight.

Lint can confirm you waited on a signal; it cannot tell you it was the wrong
signal, that two specs are competing for the same tenant, or that a test asserts
something true but irrelevant. Semantic flakiness and weak assertions remain a
review and design problem.

It is also possible to overshoot: a fixture layer opinionated enough that people
write worse tests to satisfy it, or an abstraction library that becomes the
second application this skill exists to prevent. When a rule is fighting a
legitimate case repeatedly, that is evidence about the rule.
