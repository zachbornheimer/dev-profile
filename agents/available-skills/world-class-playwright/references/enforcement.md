# Enforcement

How each rule in SKILL.md is made mechanical. Read this when standing up
guardrails, adding a rule, or adopting the standard in an existing suite.

The organizing idea: **rank mechanisms by strength and always reach for the
strongest one available.** A rule enforced structurally cannot be violated; a
rule enforced by lint can be violated with a visible, greppable override; a rule
enforced by review is violated whenever the reviewer is tired.

| Strength | Mechanism                                  | Violation looks like                    |
| -------- | ------------------------------------------ | --------------------------------------- |
| 1        | Structural — the wrong call is unreachable | Impossible                              |
| 2        | Compile-time — types reject it             | Build error, instant                    |
| 3        | Lint — AST rejects it                      | Build error, overridable with a comment |
| 4        | CI gate — the suite as a whole rejects it  | Red build                               |
| 5        | Trend — visible but not blocking           | A number moves                          |
| 6        | Review                                     | Depends who's looking                   |

---

## 1. Structural

**The import restriction is the single highest-leverage rule in this document.**

```js
"no-restricted-imports": ["error", { paths: [{
  name: "@playwright/test",
  message: "Import from fixtures/base instead.",
}]}]
```

Scope it to `specs/`, `pages/`, `components/`, `workflows/`. Only `fixtures/`
may import Playwright directly.

Once true, the base fixture is the standardization surface: auth state,
worker-unique identity, tenant isolation, data namespaces, API clients, clock
control, cleanup registration, feature flags, diagnostics. Changing any policy
becomes one edit.

Going further — having fixtures hand specs domain objects rather than a raw
`Page` — puts `waitForTimeout` out of reach entirely, since specs never hold a
`Page`. That is genuinely expensive and starts to become the second application
this standard exists to prevent. A cheaper middle ground is to expose `page` and
restrict specific methods:

```js
"no-restricted-properties": ["error",
  { object: "page", property: "waitForTimeout", message: "See permitted waits." },
  { object: "page", property: "waitForSelector", message: "Use a locator assertion." },
]
```

## 2. Compile-time

**Branded test IDs.** Generate a union of valid IDs from application source and
type `getByTestId` against it. Stale and typo'd IDs become type errors instead of
30-second timeouts.

```ts
export type TestId = 'checkout-submit' | 'cart-line-item' | /* generated */;
export const byTestId = (page: Page, id: TestId) => page.getByTestId(id);
```

The same trick applies to feature-flag names, route names, and role names in
role-based auth fixtures. Anything with a fixed vocabulary that currently lives
in string literals is a candidate.

**`no-floating-promises` earns its place here** even though it is a lint rule: an
unawaited `expect` silently makes a test unable to fail, and it is invisible in
review because the line looks correct.

## 3. Lint

Start from `eslint-plugin-playwright`'s recommended set — verify rule names
against your installed version, they change between majors — then add house
rules. Rules that map directly onto SKILL.md:

| Rule                                            | Prevents                                                           |
| ----------------------------------------------- | ------------------------------------------------------------------ |
| `playwright/no-wait-for-timeout`                | Sleeps                                                             |
| `playwright/no-networkidle`                     | False readiness                                                    |
| `playwright/no-wait-for-selector`               | Pre-locator waiting                                                |
| `playwright/no-element-handle`                  | Handles that go stale                                              |
| `playwright/no-eval`                            | Bypassing the user contract                                        |
| `playwright/no-force-option`                    | Hiding overlays and disabled controls                              |
| `playwright/no-nth-methods`                     | Positional locators                                                |
| `playwright/no-raw-locators`                    | CSS in specs                                                       |
| `playwright/no-conditional-in-test`             | Branching that hides untested paths or optionalizes required state |
| `playwright/no-conditional-expect`              | Assertions that may not run                                        |
| `playwright/expect-expect`                      | Tests that assert nothing                                          |
| `playwright/prefer-web-first-assertions`        | Snapshot assertions racing the app                                 |
| `playwright/no-skipped-test`, `no-focused-test` | Committed `.only` / `.skip`                                        |
| `@typescript-eslint/no-floating-promises`       | Unawaited assertions                                               |

House rules via `no-restricted-syntax`. These correspond to defects found in real
suites, not speculative hygiene:

```js
// Boolean-blind assertions: every failure reads "expected true, received false"
{
  selector: "CallExpression[callee.property.name='toBe'][arguments.0.value=true]"
}

// Hand-rolled sleeps that no Playwright rule catches
{
  selector: "CallExpression[callee.name='setTimeout']"
}

// Swallowed errors
{
  selector: 'CatchClause[body.body.length=0]'
}
{
  selector: "CallExpression[callee.property.name='catch'] > ArrowFunctionExpression"
}

// Per-test timeout overrides — policy lives in timeouts.ts
{
  selector: "CallExpression[callee.object.name='test'][callee.property.name='setTimeout']"
}

// Module-level mutable state: the classic cross-test contamination
{
  selector: "Program > VariableDeclaration[kind='let']"
}

// Fixed identities that collide under parallelism
{
  selector: 'Literal[value=/^(test|qa)[-_.@]/i]'
}


// Serial suites: permitted only through an attributed escape hatch.
{
  selector: "CallExpression[callee.object.object.name='test'][callee.object.property.name='describe'][callee.property.name='serial']",
  message: 'Serial suites disable isolation and parallelism. Use independent setup or one journey test; document a real external constraint to override.'
}

// XPath
{
  selector: "CallExpression[callee.property.name='locator'] > Literal[value=/^(\\/\\/|xpath=)/]"
}
```

Unbounded `waitForResponse` predicates deserve a rule of their own: a predicate
that matches any response will pass on the wrong one. Require predicates to come
from the centralized `api/` layer rather than being written inline.

## 4. CI gates

The things no single file can check.

**Temporary characterization guard.** Characterization tests intentionally assert
known-wrong behavior, so interruption safety must be mechanical. Reserve one marker
(the examples use `@characterization-only`) and fail CI if it appears in executable
test files. Do not scan docs/examples, where the marker is described legitimately.
Ship the check as a repository script so local hooks and CI use the same rule.

```bash
node scripts/reject-characterization-tests.mjs tests
```

```bash
playwright test --forbid-only --fail-on-flaky-tests
playwright test --only-changed --repeat-each=5   # pre-merge, changed specs
playwright test --shard=1/4                       # sharded correctness
SHUFFLE=1 playwright test                         # order independence (nightly)
```

The `--only-changed --repeat-each` gate is the highest-value one: it catches
flake at the moment of introduction, when the author still has context, rather
than six weeks later in a triage backlog nobody owns.

Add a per-test duration budget that fails the build, so slowness cannot creep in
one 200ms at a time, and a quarantine expiry check that fails when a quarantined
test passes its owner-assigned date.

## 5. Trends

Not pass/fail — these tell you whether the suite is drifting:

- Ratio of `getByRole` : `getByLabel` : `getByTestId` : raw CSS
- Escape-hatch call sites, by rule
- Serial blocks, quarantined tests, `expect.soft` sites
- Specs bypassing the fixture layer
- Duplicate test titles
- Titles beginning with issue IDs instead of product behavior
- Body-wide text assertions and permissive locator/normalization escape hatches
- Serial suites and conditional-test suppressions introduced by generated batches
- Temporary characterization markers (must remain zero on mergeable branches)
- p50/p95 duration by tag

A rising escape-hatch count for `no-positional-locator` is usually a statement
about the product's accessibility, not about the test authors.

---

## Escape-hatch policy

Every ban needs a sanctioned, more-annoying legal path or it gets routed around
invisibly. The point of the hatch is not permission; it is **attribution and
countability**.

Standard syntax, one form everywhere:

```ts
// playwright-standard-disable-next-line no-positional-locator
// Reason: third-party date widget exposes no semantic identifiers.
// Remove when: VENDOR-1842 is resolved.
const month = calendarCells.nth(monthIndex)
```

For waits, ship a function rather than a comment, so the justification is a
runtime-checked argument and cannot be an empty string:

```ts
await unavoidableDelay(page, 500, {
  why: 'Third-party payment iframe emits no readiness event',
  ticket: 'PAY-4471',
})
```

Requirements for every exception: local, documented, greppable, linked to a
defect or architectural constraint, carrying a removal condition. A CI check
should reject a hatch with a missing or closed ticket reference.

---

## Adopting this in an existing suite

Flipping forty rules to `error` on a legacy suite produces one unmergeable PR
that gets abandoned, and teaches everyone the standard is unrealistic.

1. **Base fixture and import restriction first.** Everything else depends on
   specs funnelling through one surface. Do this before any cosmetic rule.
2. **Ratchet, don't flip.** Rules go on as `warn` with a checked-in baseline
   count; the build fails only when a count increases. Betterer does this, or a
   committed baseline file and a small script. Lower the baseline as you clean.
3. **Ship the generator early.** `scripts/new-spec.mjs` scaffolds a spec in the
   blessed shape. Most drift enters by copy-paste from a neighbouring file, not
   by ignorance of the standard — a generator beats a document.
4. **Migrate by risk, not directory.** Flakiest and slowest specs first; they are
   where the standard pays back immediately and where support is easiest to win.
5. **Track escape-hatch count from day one**, so migration debt is
   distinguishable from newly introduced debt.
6. **Re-derive the rule when it fights you.** A rule that produces frequent
   legitimate exceptions is miscalibrated. Fix the rule rather than training
   people to override it, because the override habit generalizes.
