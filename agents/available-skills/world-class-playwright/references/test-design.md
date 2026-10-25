# Test Design: Claims, Falsifiability, and Regression Quality

A green test is useful only when it would turn red for the product regression it
claims to protect against. Design that failure path before writing selectors.

## Start from a product claim

Before code, write the contract in one sentence:

> Given <relevant state>, when <user or system action>, then <observable outcome>.

Then identify:

- **Failure mode:** what concrete regression should make this test fail?
- **Observable:** what user-visible or externally observable signal proves the outcome?
- **Setup:** what is the cheapest reliable way to create the prerequisite state?
- **Layer:** unit, component, API/integration, browser UI, or visual comparison?

If those cannot be stated precisely, the test is not ready to implement.

A test may assert several facets of one coherent outcome. It should not collect
unrelated acceptance criteria merely because they came from the same ticket.

## Tickets are traceability, not test architecture

Do not mechanically create one test per issue or one giant test per issue.
Requirements and executable scenarios have different boundaries:

- One ticket may need several tests at different layers.
- Several tickets may describe one product behavior and belong in one scenario.
- Some acceptance criteria are already covered by an existing scenario and need
  no new browser test.
- Pure styling, validation logic, or service contracts may belong below E2E.

Name tests after the behavior they prove. Put issue IDs in Playwright annotations
or other repository-standard metadata, not at the front of every title.

```ts
test('payment shows the premium selected during quoting', {
  annotation: { type: 'issue', description: 'SAH-9904' },
}, async ({ payment }) => {
  // ...
})
```

When converting a batch of tickets into tests, cluster requirements by product
behavior and test layer before generating code. Also choose the owning spec file,
page/component/workflow boundary, cheapest setup path, and exact observable before
implementation. This prevents the generator from turning the work-tracking
structure into the test architecture.

## Falsifiability: prove the test can distinguish wrong from right

Every regression test must have a clear negative control: a known-bad condition
that violates its assertion. For a defect fix, the strongest practical workflow
is **characterize → falsify → fix**:

1. **Characterize — green.** Before changing production code, temporarily assert
   the observed buggy behavior and confirm the test passes. This establishes that
   the test reaches the real defect rather than a guessed proxy.
2. **Falsify — red.** Replace the temporary characterization assertion with the
   intended product contract. Without changing production code, confirm the test
   now fails for the expected assertion and useful diagnostic reason.
3. **Fix — green.** Change production code. Run the same contract test and confirm
   it passes.

This is not a replacement for ordinary TDD and is not a universally standardized
name; it is a defect-verification protocol. Its value is discriminating power: the
test has demonstrated both sides of the boundary it claims to protect.

### Characterization assertions are temporary and unmergeable

A characterization assertion intentionally encodes behavior the product should
not keep. An interrupted session must not leave that assertion looking like the
desired contract. Therefore temporary characterization tests MUST carry an
explicit executable marker and CI MUST reject that marker. The examples use
`@characterization-only`:

```ts
test('@characterization-only current checkout incorrectly accepts an expired card', async ({ checkout }) => {
  await checkout.submit(expiredCard())

  // Intentionally documents the defect only. This assertion must never merge.
  await expect(checkout.confirmation).toBeVisible()
})
```

After characterization, rewrite the same scenario as the permanent contract and
remove the marker:

```ts
test('declines an expired card without creating an order', async ({ checkout, orderApi }) => {
  const order = await checkout.submit(expiredCard())

  await expect(checkout.paymentError).toHaveText('Card has expired')
  await expect.poll(() => orderApi.countSubmitted(order.id)).toBe(0)
})
```

Do not use `test.skip`, `test.fixme`, expected-failure metadata, comments, or a
review convention as the only safeguard. Those can survive interruption while the
branch remains green. The repository should ship a small CI check that fails if a
temporary characterization marker exists under executable test paths.

When the exact pre-fix state is unavailable, prefer, in order:

1. Use a narrowly controlled fixture/mock to create the broken state when that
   does not change the behavior being validated.
2. Temporarily perturb the product locally to violate the contract.
3. Inspect a deliberately generated assertion failure for diagnostics and
   explicitly note that exact regression detection was not mechanically verified.
   Changing only the expected value is not equivalent to falsifying the product
   contract; it proves only that the assertion executes.

The purpose is not mutation-testing theater. It is to catch vacuous assertions,
wrong-element locators, optionalized preconditions, weak proxies, and tests that
pass for unrelated reasons.

A test that has never been observed failing is not automatically wrong, but a new
regression test whose failure mode has never been checked is unfinished.

## Preconditions are assertions, not conditionals

If the behavior requires a state, prove that the state exists before asserting
what happens inside it.

```ts
await expect(checkout.dialog).toBeVisible()
await expect(checkout.submitButton).toBeEnabled()
```

Do not turn required states into optional branches:

```ts
// Wrong: a missing product contract becomes a green test.
if (await checkout.dialog.count()) {
  await expect(checkout.submitButton).toBeEnabled()
}
```

Conditional logic is appropriate only when variability is itself part of the
product contract and each supported branch is tested deliberately.

For absence assertions, first wait for a positive readiness signal that proves
the relevant surface finished loading.

## The scenario must know its expected outcome

For deterministic input and configuration, the test should know which outcome is
correct before it runs. Assertions such as "A or B or error" usually mean the
scenario has not controlled its dependencies or has not defined its contract.

Do not use fallback locators or result unions merely to support whichever UI the
run happens to produce:

```ts
// Wrong when this configuration has one expected action.
const action = saveButton.or(submitButton).first()

// Wrong when fixed input should produce one deterministic result.
await expect(result).toContainText(/approved|declined|try again/)
```

If several outcomes are genuinely supported, encode the cause of each outcome in
explicit test data/configuration and test them separately or parameterize them.
If an uncontrolled external system makes the result nondeterministic, isolate or
mock that boundary for the product behavior test and keep separate coverage of
the real integration.

## Assert the strongest observable contract

Prefer the narrowest assertion that directly proves the claim:

- Scope to the owning region, row, dialog, form, or component.
- Assert the exact role, accessible name, value, text, state, URL, request, or
  server-side outcome that matters.
- Prefer `toHaveText`, `toHaveValue`, `toBeChecked`, `toHaveURL`, or a domain
  matcher over converting a page to text and searching it.
- Prefer exact values when the product contract is exact. Use regex or
  normalization only when the allowed variation is intentional and named.
- If a value can appear in several places, identify the correct owner before
  asserting it.
- Translate the requirement literally. If the contract says "full width," compare
  against the owning container or use a visual assertion; an arbitrary minimum
  such as `>= 200px` does not prove full width. If the contract says "at least
  44px," a numeric minimum does express the requirement.
- Resolve environment-specific expected values from typed configuration/fixtures.
  Do not widen a regex with placeholders or alternate hosts until something
  matches.

Avoid broad heuristics such as `body.innerText()`, "any money-looking string",
or a regex that can match several unrelated surfaces. Those tests often pass for
the wrong reason.

## Implementation details require a reason

A browser test should normally see what the user sees. CSS classes, framework
internals, generated IDs, private answer keys, internal component names, and DOM
shape are not contracts merely because they are easy to query.

Assert an implementation detail only when that detail is intentionally part of
the contract being protected, for example:

- a stable test id created specifically as an automation contract;
- a DOM/API integration boundary consumed by another system;
- an accessibility attribute whose semantics are the behavior;
- a CSS/layout primitive when the regression is specifically about rendering
  mechanics and no stronger user-visible invariant exists.

When such an assertion is necessary, isolate the selector in the owning page or
component object and state why the implementation detail is load-bearing.

## Visual and layout regressions need the right instrument

Choose the cheapest test that measures the real failure:

- **Component test:** local rendering or interaction state.
- **Visual comparison:** pixels, clipping, overlap, spacing, color, or complex
  composition are the contract.
- **Geometry assertion:** a stable measurable invariant such as containment,
  alignment, minimum hit target, or fixed center is the contract.
- **Full browser journey:** the defect depends on application integration,
  routing, real browser layout, or cross-surface state.

Do not replace a visual regression with a weak proxy such as "the wrapper's x/y
did not change" unless that is actually the behavior users depend on.

Pin the rendering environment for screenshot baselines and keep visual tests in
an appropriate project. Do not loosen screenshot or geometry tolerances merely
until CI passes; tolerances express product intent.

## Transient states must be controllable

Loading states, skeletons, optimistic states, animations, transitions, and
progress UI are easy to test incorrectly because they disappear.

Install control before triggering the state, then hold it long enough to inspect
it. Prefer an application-owned test seam, a narrowly mocked/stalled dependency,
or controlled time when time is truly the driver.

The pattern is:

1. Arrange deterministic control.
2. Trigger the state.
3. Assert the state is present.
4. Assert its observable invariant.
5. Release the state and, when relevant, assert the durable result.

Never sleep and hope to catch the state. Never wait for the state to disappear
and then claim to have tested its behavior.

## Generated and bulk-written tests require an audit pass

Code generation is useful for mechanics, not for deciding whether an assertion
actually proves the requirement. A batch is not complete because every ticket
has a green spec.

Before generating many tests:

1. Read existing coverage, repository instructions, config, fixtures, pages,
   components, workflows, and API/setup primitives.
2. Build a scenario map grouped by product behavior, not by ticket.
3. For each unique scenario choose the lowest reliable layer, owning spec/surface,
   setup path, observable outcome, and traceability metadata.
4. Merge duplicate claims and split unrelated acceptance criteria before code.
5. Identify repeated UI regions that belong in page/component objects, repeated
   cross-surface navigation that belongs in workflows, and lifecycle/setup that
   belongs in fixtures or API clients.
6. Check that every planned browser test can run independently from a clean
   context; redesign any plan that requires a previous test's page state.

After generation, audit the batch for systemic false-positive patterns:

- issue IDs used as the primary test organization;
- giant tests containing unrelated acceptance criteria;
- `.first()`, `.last()`, `.nth()`, or `.or(...).first()` suppressing ambiguity;
- styling classes or framework internals in specs;
- `body.innerText()` or unscoped text searches;
- conditional assertions or `clickIfPresent`-style behavior;
- serial suites or shared mutable `Page` objects;
- per-test timeout inflation;
- duplicated traversal logic instead of a named workflow;
- broad regexes or normalization that make several wrong values acceptable;
- tests whose setup dominates the behavior under test.

Then sample deliberate failures across each recurring test pattern, not just one
file. A generator can reproduce the same conceptual mistake hundreds of times.

## Review question

For every test, a reviewer should be able to answer in under a minute:

> What product regression makes this fail, and which assertion proves it?

If the answer depends on reading selector mechanics or guessing why a heuristic
was chosen, redesign the test.
