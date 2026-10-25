# Stability and Diagnostics

## The synchronization model

Web-first assertions and locator actions retry against the live page until the condition holds or the timeout expires. Generic matchers check once against an already-resolved value. Almost every timing flake is a value resolved too early:

```ts
// Races: isVisible() snapshots once, then the assertion checks a stale boolean.
expect(await locator.isVisible()).toBe(true)

// Retries until the page actually reaches the state.
await expect(locator).toBeVisible()
```

Escalation ladder when a built-in matcher doesn't fit:

1. Built-in web-first assertion (`toBeVisible`, `toHaveText`, `toHaveCount`, `toHaveURL`…) — always first choice.
2. `expect.poll(() => fn())` — retry a value-producing function, e.g. polling an API for a server-side outcome.
3. `expect(async () => { ... }).toPass()` — retry a block of coupled checks that must pass together. Use sparingly; wrapping _actions_ in `toPass` is a retry-until-success loop that masks product races.
4. A wait on an explicit signal: `page.waitForURL`, `waitForResponse`, download/popup events, or an application-specific readiness hook.

Never on the ladder: `waitForTimeout`, sleeps, `networkidle` as a general readiness definition, timeout inflation.

An explicit delay is permitted only when testing time-dependent behavior against an external system with no observable readiness signal — and it must carry a comment explaining why no deterministic signal exists.


## Transient state synchronization

A transient UI state is still a required state. Loading indicators, skeletons,
optimistic states, transitions, progress surfaces, and animations must not be
tested by racing them.

Arrange deterministic control before the action that triggers the state. Prefer
an application readiness/test seam, a narrowly controlled network dependency,
or `page.clock` when JavaScript time is actually the driver. Then:

1. Trigger the state.
2. Positively assert that it is present.
3. Assert the user-visible invariant while the state is controlled.
4. Release the state and assert the durable outcome when relevant.

Never guard the assertion with `if (await locator.count())`; if the state is
required, absence is a test failure. Never wait for a transient state to be gone
and then claim to have validated its rendering or motion.

For visual motion/layout bugs, measure the element and invariant users actually
experience. A stable wrapper does not prove that a moving child is correct.
Choose component, visual comparison, geometry, or full browser coverage based on
which layer can reproduce the defect without irrelevant setup.

## Known API traps

**`locator.all()` does not auto-wait.** It snapshots the DOM at that instant; if the list is still loading you iterate a partial result. Pin the count first:

```ts
const items = page.getByRole('listitem')
await expect(items).toHaveCount(5)
for (const item of await items.all()) {
  /* ... */
}
```

**Missing `await` races the action against the rest of the test.** An un-awaited `click()` or `fill()` runs concurrently with subsequent steps and fails nondeterministically. Enforce `@typescript-eslint/no-floating-promises` in lint — this single rule prevents an entire flake class.

**Strict mode violations are signal.** A locator matching two elements means the contract is ambiguous. Scope to the owning region (`.filter()`, component roots) instead of silencing with `.first()`.

## Time-dependent behavior: `page.clock`

Timers, session expiry, debounces, scheduled UI, and animations are the classic justification for sleeps. `page.clock` removes it — install a fake clock and control time deterministically:

```ts
test('session expiry banner appears after 30 minutes idle', async ({ page }) => {
  await page.clock.install({ time: new Date('2026-01-15T10:00:00') })
  await page.goto('/dashboard')

  await page.clock.fastForward('30:00') // 30 minutes, instantly

  await expect(page.getByRole('alert')).toHaveText(/session is about to expire/i)
})
```

- `clock.install({ time })` — start faked time.
- `clock.fastForward(ticks)` — jump ahead, firing due timers.
- `clock.pauseAt(date)` — freeze at a moment (also makes animated screenshots deterministic).
- `clock.setFixedTime(date)` — pin `Date.now()` for date-sensitive rendering.

A test that waits in real time for a product timer is both slow _and_ flaky; a faked clock is neither.

## Diagnostics

The suite's value is realized at failure time. A CI failure should normally include: test title and annotations, browser/project, URL, trace, failure screenshot, retained video when useful, relevant console errors, failed network requests, the domain identifiers needed to inspect server state, and a concise business-level step history.

- `trace: 'on-first-retry'` gives full time-travel debugging exactly when needed without taxing green runs.
- Use an automatic fixture to collect console/network logs and attach them only on unexpected outcomes.
- Never dump secrets, tokens, full customer data, or unrestricted response bodies into artifacts.

Use `test.step` for meaningful business operations — it makes the failure location legible in reports and traces:

```ts
await test.step('Submit an expired payment card', async () => {
  await checkout.payment.enterCard(expiredCard())
  await checkout.submit()
})
```

Do not wrap every locator call in a step; that produces noise, not signal.

When enriching an error, preserve the original as `cause` — the business context tells the reader _what_ failed, the cause tells them _why_:

```ts
try {
  await this.submitButton.click()
} catch (error) {
  throw new Error('Failed to submit checkout order', { cause: error })
}
```

## Flaky-test remediation

A flaky test is a defect with a root cause — in the test, the suite architecture, or the product itself. The remediation loop:

1. **Reproduce** with trace on and repeated execution: `npx playwright test path/to/spec --repeat-each=20`, and again with full parallelism, since many flakes only appear under contention.
2. **Classify** the failure:
   - Selector ambiguity (strict-mode or wrong-element symptoms).
   - Missing readiness signal (assertion ran before the app settled).
   - Shared-state or test-data collision (fails only in parallel → isolation bug).
   - Product race condition (the app itself is nondeterministic — file the bug; the test found something real).
   - External dependency instability (consider a mock at that boundary + a separate real-integration test).
   - Resource exhaustion (worker count vs. CI capacity).
   - Incorrect assertion (asserting mechanics instead of outcome).
   - False positive (required state optionalized, wrong element selected, broad text/value heuristic, or assertion satisfied by an unrelated surface).
3. **Fix the underlying contract**, not the symptom.
4. **Prove the fix**: repeated runs, parallel runs, then remove any temporary retries/quarantine.
5. **Keep it visible**: a test that passed on retry stays flagged as flaky in reporting until fixed. Retries are how you _collect evidence_ (the retry's trace), never how you define success.

Never "fix" flakiness by: adding sleeps, raising timeouts globally, force-clicking through overlays, catching the error, looping the action until it works, making tests serial, filling extra fields, or disabling the assertion. Every one of these converts a visible defect into an invisible one.

A force click (`{ force: true }`) is permitted only when the test specifically validates behavior that cannot be triggered through normal actionability, with the reason documented — otherwise it bypasses the exact checks (visible, stable, receives events) that make tests meaningful.

## Structural assertions: aria snapshots

For asserting a region's semantic structure (menus, tables, complex composites), `toMatchAriaSnapshot` sits at the right altitude: it verifies the accessibility tree in YAML, is deterministic across OS and font rendering (unlike pixel screenshots), ignores pure styling churn (unlike DOM snapshots), and produces human-readable diffs:

```ts
await expect(page.getByRole('navigation')).toMatchAriaSnapshot(`
  - navigation:
    - link "Home"
    - link "Products"
    - link "Cart"
`)
```

Use pixel screenshots (`toHaveScreenshot`) only for genuinely visual risk (layout, color), pinned to one rendering environment (e.g., a fixed Docker image) and kept in a dedicated project with resource blocking disabled.

## Accessibility as a stability strategy

Semantic locators double as accessibility feedback. A control that can't be located by role/label may indicate a real accessibility defect — escalate missing names, labels, and incorrect roles to the product team rather than compensating indefinitely with brittle CSS. Include keyboard, focus, and screen-reader-oriented tests where those behaviors carry product risk; integrate a proven accessibility engine (e.g. axe) rather than hand-rolling a scanner in Playwright helpers.
