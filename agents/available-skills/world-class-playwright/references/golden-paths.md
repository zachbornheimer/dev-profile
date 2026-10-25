# Golden paths

Canonical implementations for recurring situations. Without these, every
engineer interprets the principles differently and the suite grows fifteen
versions of the same wait.

Each entry states the trap first, because the trap is why the pattern exists.

---

## Action that triggers navigation, popup, download, or response

**Trap:** acting first, then waiting, loses the event when it fires fast.

```ts
const [download] = await Promise.all([
  page.waitForEvent('download'),
  page.getByRole('button', { name: 'Export CSV' }).click(),
])
expect(download.suggestedFilename()).toBe('orders.csv')
```

Same shape for `waitForEvent('popup')` and `context.waitForEvent('page')`.
Prefer asserting on resulting UI state over asserting on the event itself.

## Response predicates

**Trap:** an inline predicate that matches any response passes on the wrong one.

Own predicates in `api/`, never inline in a spec:

```ts
export const ordersApi = {
  confirmed: (r: Response) =>
    r.url().endsWith('/orders/confirm') && r.request().method() === 'POST' && r.ok(),
}

const [response] = await Promise.all([page.waitForResponse(ordersApi.confirmed), checkout.submit()])
```

## Eventual consistency

**Trap:** fifteen hand-rolled versions of "wait until the order is ready."

One domain-owned primitive per concept, with the backend budget from
`timeouts.example.ts`:

```ts
await ordersApi.waitForStatus(orderId, 'confirmed')
```

Implement it once with `expect.poll` against the API, not the UI.

## Authentication

**Trap:** logging in through the UI in every test.

Log in once per role in a setup project, save `storageState`, reuse it. Keep one
UI login test that actually exercises the login form — that behavior still needs
coverage, just not 400 times.

## Dynamic tables

**Trap:** `rows.nth(3)` breaks the moment sort order or data changes.

Locate by content, scoped to the region:

```ts
const row = ordersTable.getByRole('row').filter({ hasText: orderId })
await expect(row.getByRole('cell', { name: 'Confirmed' })).toBeVisible()
```

When the _structure_ is the contract, `toMatchAriaSnapshot` beats cell-by-cell
assertions and survives styling churn.

## Virtualized lists

**Trap:** asserting absence when the item merely isn't rendered yet.

Scroll to the item via the application's own search/filter rather than
`scrollIntoViewIfNeeded` loops. If no such affordance exists, that is a product
gap worth raising: users have the same problem.

## Clock-controlled behavior

**Trap:** waiting 30 real seconds for a session to expire.

```ts
await page.clock.install()
await page.clock.fastForward('30:00')
await expect(page.getByRole('alert', { name: /session expired/i })).toBeVisible()
```

Also the correct tool for debounce, polling intervals, and scheduled UI.

## File upload

```ts
await page.getByLabel('Attach invoice').setInputFiles(builders.invoicePdf())
```

Never automate the OS file dialog. Generate fixtures from builders so the file's
contents are known to the assertions.

## Email / background job completion

**Trap:** sleeping until the mail probably arrived.

Query the mail catcher or job API through the `api/` layer with a domain
primitive: `await mail.waitForMessage({ to: user.email, subject: /Welcome/ })`.

## Third-party widgets

**Trap:** compensating indefinitely with brittle CSS.

Prefer stubbing the widget at the network boundary and testing your integration
contract. When you must drive the real one, isolate every brittle locator inside
one component object, with an escape-hatch comment naming the vendor ticket.

## Feature flags

Flags come from a fixture, never from ambient environment state, so a test
declares the configuration it needs and cannot be affected by another test's.

```ts
test('new checkout', async ({ flags, page }) => {
  await flags.enable('checkout-v2')
  // ...
})
```

## Asserting an absence

**Trap:** a passing assertion that something never appeared, when the page hadn't
finished loading.

Anchor to a positive signal first, then assert the negative:

```ts
await expect(page.getByRole('heading', { name: 'Order complete' })).toBeVisible()
await expect(page.getByRole('alert')).toHaveCount(0)
```

## Transient UI states

**Trap:** checking a loading/transition state only if it happens to still be
visible. Fast runs skip the assertion; slow runs inspect an arbitrary moment.

Install deterministic control before triggering the state, assert entry into the
state, assert its observable contract, then release the control. Use a narrow
application/test seam or one specific mocked/stalled dependency. Use
`page.clock` only when JavaScript time is the behavior being controlled.

```ts
await loadingGate.hold()
await application.open()
await expect(application.preparingStatus).toBeVisible()
await expect(application.preparingStatus).toHaveAccessibleName('Preparing application')
// Assert the actual layout/visual/interaction invariant here.
await loadingGate.release()
```

The gate belongs in a fixture/workflow/API boundary, not copied into every spec.
Do not sleep and hope to catch the state; do not conditionalize required
assertions.

## Regression test negative control

**Trap:** a new test goes green, but nobody verifies that the assertion detects
the defect rather than an unrelated signal.

For a defect fix, prefer **characterize → falsify → fix**:

1. Temporarily assert the current defect and observe green. Mark this executable
   test `@characterization-only`; CI must reject that marker.
2. Rewrite the assertion as the desired product contract without changing the
   implementation and observe red for the intended reason.
3. Fix production code and observe the same permanent contract green.

The temporary first green proves the test reaches the defect. The red proves the
permanent assertion distinguishes the defect from the desired behavior. The final
green proves the implementation now satisfies that same contract.

If the known-bad implementation is unavailable, use a narrowly broken fixture or
local perturbation. Do not call a changed expected value equivalent evidence.

This is especially important for generated batches: sample each recurring pattern
because one weak locator or heuristic can be replicated across dozens of specs.
