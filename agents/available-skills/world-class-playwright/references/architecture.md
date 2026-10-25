# Architecture

Use the smallest architecture that preserves clear ownership. Every layer below exists to give one kind of change one place to land: a UI change touches a page object, an auth change touches a fixture, a scenario change touches a spec. When a change fans out across layers, ownership is wrong.

```text
tests/
  checkout/
    submit-order.spec.ts
    payment-validation.spec.ts

playwright/
  fixtures/
    test.ts                    # merged fixture export; specs import from here
    auth.fixture.ts
    data.fixture.ts
  pages/
    checkout.page.ts
  components/
    address-form.component.ts
    payment-form.component.ts
  workflows/
    place-order.workflow.ts
  api/
    orders.client.ts
    users.client.ts
  data/
    user.builder.ts
    order.builder.ts
  support/
    diagnostics.fixture.ts
    errors.ts
```

Don't create layers speculatively. A 20-test suite may need only specs + fixtures + one page object. Add components when a UI region repeats, workflows when a journey repeats, API clients when UI setup gets expensive. Premature layering is how test suites become the "second application" the governing principle warns against.

## Design the test topology before the tests

For a batch of requirements, defects, or generated tests, decide the topology
before writing selectors. Build a small scenario map with these fields:

| Product claim | Owning surface | Layer | Setup | Observable | Traceability |
| --- | --- | --- | --- | --- | --- |
| unsupported state is rejected inline | quote form | browser/component | open quote directly | state error under field | SAH-… |
| selected premium appears at payment | payment | browser/integration | API/deep state | premium value in payment summary | SAH-… |

The exact format is unimportant; the decisions are. Use the map to:

- group tests by product capability rather than issue number;
- collapse duplicate requirements into one scenario;
- split one ticket when its acceptance criteria belong to different surfaces or
  layers;
- decide which expensive journeys should become workflows and which setup should
  bypass the UI;
- make file ownership obvious before generated code creates accidental structure.

A generated directory such as `issues-9895-9907.spec.ts` is a warning sign. Prefer
cohesive files such as `quote.spec.ts`, `payment.spec.ts`, and `signing.spec.ts`
when those are the product boundaries. Do not create a directory per ticket unless
the repository's actual product architecture is ticket-shaped (rare).

## Specs

Specs own: scenario intent, the input values that matter, business-level actions, business-level assertions, tags/annotations, and the visible link between the scenario and the product claim it protects.

Specs do not own: repeated selector mechanics, authentication implementation, generic data provisioning, navigation algorithms, failure-artifact plumbing, or ticket-by-ticket orchestration.

A good test reads like executable product behavior:

```ts
test('declines an expired card without creating an order', async ({ checkout, orderApi }) => {
  const draft = await orderApi.createDraft()
  await checkout.open(draft.id)

  await checkout.payment.enterCard(expiredCard())
  await checkout.submit()

  await expect(checkout.payment.error).toHaveText('Card has expired')
  await expect.poll(() => orderApi.countSubmitted(draft.id)).toBe(0)
})
```

Note what makes this readable: the fixture names (`checkout`, `orderApi`) inject exactly what the test needs; `expiredCard()` names the scenario-critical data; the final assertion verifies the server-side outcome (no order created), not just the UI message.

### Scenario boundaries

Organize specs around product behavior, not work-tracking structure. Issue IDs
belong in annotations or repository metadata. A ticket with six unrelated
acceptance criteria is not one six-purpose test; several tickets describing the
same behavior are not automatically several browser tests.

A scenario should have one coherent reason to fail. Several assertions are fine
when they prove facets of the same outcome. If the title needs "and" to connect
unrelated product claims, split it or move lower-level checks to the appropriate
layer.

Do not split one long-lived browser session into several nominal tests just to get
more test names. If test B requires the mutated page left behind by test A, they
are one scenario disguised as several tests. Either provision the required state
independently for each scenario or keep the irreversible journey as one test with
`test.step` boundaries.

Before implementing a regression test, state the failure mode and the strongest
observable that would distinguish correct from broken behavior. See
`test-design.md`.

## Fixtures

Fixtures are Playwright's dependency-injection system. Because they're requested by name, Playwright runs only the setup a test actually needs — this is why fixtures beat `beforeEach` blocks for anything shared: unrelated specs stay fast, and teardown ordering is automatic.

Fixtures own: authentication state, test-scoped pages and clients, worker-scoped partitioned resources, setup/cleanup that belong together, automatic failure diagnostics, typed configuration options.

Fixtures MUST NOT become hidden scenario scripts. A fixture may construct a `CheckoutPage`; it should not silently complete checkout before every test unless every consumer explicitly requires that exact state. When a fixture performs invisible navigation, every test that uses it inherits invisible assumptions.

```ts
import { test as base } from '@playwright/test'

type TestFixtures = {
  checkout: CheckoutPage
  orderApi: OrderApi
}

type WorkerFixtures = {
  workerAccount: Account
}

export const test = base.extend<TestFixtures, WorkerFixtures>({
  // One account per worker: parallel tests never collide on server state.
  workerAccount: [
    async ({}, use, workerInfo) => {
      const account = await provisionWorkerAccount(workerInfo.workerIndex)
      try {
        await use(account)
      } finally {
        await deleteWorkerAccount(account.id)
      }
    },
    { scope: 'worker' },
  ],

  checkout: async ({ page }, use) => {
    await use(new CheckoutPage(page))
  },

  orderApi: async ({ request, workerAccount }, use) => {
    await use(new OrderApi(request, workerAccount))
  },
})

export { expect } from '@playwright/test'
```

Scope guidance:

- Test-scoped by default — isolation is free.
- Worker-scoped only when setup is expensive, the resource is safely reusable, mutable access is partitioned by worker, cleanup is reliable, and the performance win is _measured_.
- Automatic fixtures (`auto: true`) only for truly universal behavior such as failure diagnostics — never scenario-specific assertions.
- Keep fixture graphs shallow and dependencies visible in types.
- Give slow fixtures their own timeout rather than inflating every test's timeout.

## Page objects

A page object represents one cohesive browser surface. It owns stable locators, page-specific interactions, page readiness, and small local invariants. It does not own end-to-end journeys, global test data, branching across unrelated pages, generic "fill every field" behavior, or reporting.

```ts
import { expect, type Locator, type Page } from '@playwright/test'

export class CheckoutPage {
  readonly payment: PaymentForm
  readonly submitButton: Locator

  constructor(private readonly page: Page) {
    this.payment = new PaymentForm(page.getByTestId('payment-form'))
    this.submitButton = page.getByRole('button', { name: 'Place order' })
  }

  /** Opens a checkout session and verifies the page contract. */
  async open(checkoutId: string): Promise<void> {
    await this.page.goto(`/checkout/${encodeURIComponent(checkoutId)}`)
    await expect(this.submitButton).toBeVisible()
  }

  /** Submits the current order. Outcome assertions remain in the test. */
  async submit(): Promise<void> {
    await this.submitButton.click()
  }
}
```

Keep methods intention-revealing and small. Cohesion, not line count, is the size limit: a page object spanning unrelated pages is a god object regardless of length.

## Component objects

Use component objects for reusable UI regions with their own behavior: address forms, date inputs, data grids, modals, navigation bars, upload controls.

Scope every child locator to the component root — this is what makes the component reusable across pages and safe when the region repeats:

```ts
import type { Locator } from '@playwright/test'

export class AddressForm {
  constructor(private readonly root: Locator) {}

  async complete(address: Address): Promise<void> {
    await this.root.getByLabel('Address line 1').fill(address.line1)
    await this.root.getByLabel('City').fill(address.city)
    await this.root.getByLabel('State').selectOption(address.stateCode)
    await this.root.getByLabel('ZIP code').fill(address.postalCode)
  }
}
```

## Workflows

A workflow coordinates multiple pages or components to perform a reusable business journey: authenticate a role through the UI, reach checkout from a cart, complete a multi-step application, create-and-approve a record across roles.

Workflows own orchestration, not locator details. A workflow exposes explicit inputs and outputs; it never guesses values for unknown screens or fields. (For flows where the screens themselves vary, read `dynamic-wizards.md`.)

## API clients

API clients own test setup and server-side verification — the alternative to slow, failure-prone UI setup.

- Validate response status and schema; a 500 during setup should fail fast with the request context, not surface later as a mysterious UI state.
- Return domain objects, not raw response bodies.
- Keep authentication explicit.
- Do not duplicate production business logic in the test suite — call the product's API, don't reimplement its rules.

## Builders

Builders provide valid defaults without hiding scenario-critical values:

```ts
export function buildApplicant(overrides: Partial<Applicant> = {}): Applicant {
  return {
    firstName: 'Avery',
    lastName: `Test-${crypto.randomUUID()}`,
    email: `e2e+${crypto.randomUUID()}@example.test`,
    dateOfBirth: '1985-05-05',
    ...overrides,
  }
}
```

The UUID suffixes are not decoration — they're what makes parallel execution safe. The overrides parameter is what lets the test declare which values the scenario depends on.

## Code quality

- TypeScript strict mode for new suites unless the repository documents a constraint.
- Explicit domain types; avoid `any` — use `unknown` and narrow.
- Locators `readonly`.
- Prefer meaningful outcome types over Boolean blindness:

```ts
type SubmissionResult =
  | { kind: 'confirmed'; orderId: string }
  | { kind: 'declined'; reason: string }
```

Avoid `Promise<boolean>` / `Promise<string | null>` returns unless the two outcomes are self-evident and no diagnostic information is lost.

- Separate optional-element discovery from required action:

```ts
async hasPromotionBanner(): Promise<boolean> {
  return this.promotionBanner.isVisible();
}

async dismissPromotionBanner(): Promise<void> {
  await expect(this.promotionBanner).toBeVisible();
  await this.promotionBanner.getByRole('button', { name: 'Dismiss' }).click();
}
```

Do not create `clickIfPresent()` as a universal primitive — it converts "the product changed" into silence.

- Comments explain constraints and reasons, not syntax. Workarounds link to a defect or state a removal condition.
- Remove dead selectors, stale workarounds, commented-out test code.
