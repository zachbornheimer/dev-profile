# Dynamic Wizards and Variable Page Sequences

Multi-step flows whose screens vary by product configuration, user data, or feature flags tempt teams toward one giant loop of broad selectors, generic input values, and ignored failures ("fill whatever's on screen, click Next until done"). That design _cannot fail usefully_: when the product adds a screen, changes a field, or breaks a step, the loop guesses its way through and the suite goes green over a broken product — the worst possible outcome.

Model the wizard instead as explicit states with independently testable handlers.

## Step handlers

```ts
interface WizardStepHandler {
  readonly id: string

  /** Returns true only when this handler owns the active step. */
  matches(page: Page): Promise<boolean>

  /** Completes the active step using explicit domain data. */
  complete(page: Page, data: ApplicationData): Promise<void>
}
```

Each handler owns one screen's contract: how to recognize it (a heading, a URL segment, a landmark — something specific, not body-wide text) and how to complete it with _named domain values_. Handlers are small, reviewable, and testable in isolation.

## The registry and orchestrator

```ts
const handlers: readonly WizardStepHandler[] = [
  applicantStep,
  coverageStep,
  evidenceStep,
  beneficiariesStep,
  signatureStep,
]
```

The orchestrator must, on every iteration:

1. Identify exactly one active handler — **fail if zero match** (unknown screen = product contract change) and **fail if multiple match** (ambiguous recognition contract).
2. Record the step ID (feeds the step history in diagnostics).
3. Run the handler.
4. Observe a deterministic transition before re-evaluating (the next screen's readiness signal, not a sleep).
5. Enforce a finite transition limit and detect repeated states — an infinite or cycling wizard should fail with its step history, not hang until the test timeout.
6. Attach diagnostics on failure.

The orchestrator must never: fill every empty input, pick the first visible radio/option, continue after a required interaction fails, treat body-wide text matching as the only state contract, or silently recover from an unknown page.

## Unknown steps are findings, not obstacles

An unrecognized screen means the product changed. That is exactly what the suite exists to catch, so make the failure actionable:

```text
Unknown wizard step
URL: /application/123
Heading: Employment information
Progress: 42%
Visible controls: Employer name, Occupation, Annual income
```

Whoever reads this failure can write the missing handler in minutes. Whoever debugs a generic-autofill loop that silently "handled" the same screen may never learn it happened.

## Data flows down explicitly

The wizard takes one typed `ApplicationData` (built via a builder with valid defaults + scenario overrides — see `architecture.md`). Handlers consume the fields they own. A newly required field must produce an actionable failure until the scenario defines its value; auto-filling it with a fallback hides a contract change and can mask real validation behavior.
