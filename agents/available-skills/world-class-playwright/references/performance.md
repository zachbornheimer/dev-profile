# High-Performance Strategy

Speed work has a strict order of operations. Each level typically dwarfs the ones below it, so optimize top-down:

1. **Delete work** — UI setup replaced by API calls, logins replaced by stored auth state, tests moved to cheaper layers (see `review.md` § Test Portfolio).
2. **Parallelize work** — workers on one machine, then shards across machines.
3. **Trim per-action cost** — resource blocking, navigation waits, headless mode.

Teams that start at level 3 save milliseconds while level 1 leaves minutes on the table.

## Level 1: Remove UI work

The fastest reliable UI action is the one the test does not perform. For every setup step ask:

1. Is this behavior under test? If not, it should not go through the UI.
2. Can an API create this state?
3. Can authentication state be reused?
4. Can the test begin at a deep link instead of navigating there?

### Authentication — the single largest win in most suites

Logging in through the UI per test is typically the biggest hidden cost: at 3–5 seconds per login, a 200-test suite spends 10+ minutes typing passwords, hammers auth rate limits, and adds a failure point unrelated to anything under test. Two canonical patterns fix this; choose by whether tests mutate server-side state.

**Pattern A — shared state via setup project** (for tests that don't modify server-side state tied to the account):

```ts
// playwright.config.ts
export default defineConfig({
  projects: [
    { name: 'setup', testMatch: /.*\.setup\.ts/ },
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'], storageState: 'playwright/.auth/user.json' },
      dependencies: ['setup'],
    },
  ],
})

// auth.setup.ts — runs once before the suite
import { test as setup, expect } from '@playwright/test'

setup('authenticate', async ({ page }) => {
  await page.goto('/login')
  await page.getByLabel('Email').fill(process.env.E2E_EMAIL!)
  await page.getByLabel('Password').fill(process.env.E2E_PASSWORD!)
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible()
  await page.context().storageState({ path: 'playwright/.auth/user.json' })
})
```

**Pattern B — one account per worker** (required when tests mutate server-side state, so parallel workers never collide): override the `storageState` fixture at worker scope, keyed by `testInfo.parallelIndex`, authenticating each worker once with its own account. See the fixture example in `architecture.md` for the worker-account shape; the auth version saves `storageState` per worker instead of logging in per test.

In both patterns:

- Authenticate via API instead of UI form when the app supports it — faster still.
- Test the login flow itself separately, through the UI, as its own scenario.
- Write per-run state under the project `outputDir` (auto-cleaned); delete persisted state when it expires.
- Never commit secrets or auth files.

### Deep links

Start the test at `/checkout/{id}` created via API, not at the homepage followed by six navigation clicks. Navigation you didn't perform can't flake and costs nothing.

## Level 2: Parallelism

Design every test for parallel execution from the beginning — retrofitting isolation onto a serial suite is far more expensive than building it in. Parallel execution doesn't create shared-state problems; it exposes them. A test that fails only in parallel has an isolation bug to fix, not flakiness to suppress.

- Unique users, tenants, records, filenames, idempotency keys per test (builders with UUIDs).
- Partition genuinely shared accounts by `workerIndex` / `testInfo.parallelIndex`.
- Keep tests inside a file independent so `fullyParallel: true` remains viable.
- Never rely on queue order or test-file execution order.
- Avoid global locks; when unavoidable, isolate those tests in a clearly named project.

### Workers before shards

Workers parallelize on one machine; shards distribute across machines. Exhaust workers first — sharding adds CI complexity and per-shard startup overhead that only pays off at scale:

- **Suite under ~2 minutes / under ~50 tests**: don't shard. Tune `workers` to the runner's cores.
- **~50–200 tests**: 2–4 shards usually give the best return.
- **200+ tests**: shard aggressively, 4–8 shards, and measure balance.

### Sharding with merged reports

Each shard's default HTML report would overwrite the others. Use the blob reporter per shard and merge:

```ts
// playwright.config.ts
reporter: process.env.CI ? 'blob' : 'html',
```

```yaml
# GitHub Actions sketch
jobs:
  test:
    strategy:
      fail-fast: false          # one failing shard must not cancel the rest
      matrix: { shardIndex: [1, 2, 3, 4], shardTotal: [4] }
    steps:
      - run: npx playwright test --shard=${{ matrix.shardIndex }}/${{ matrix.shardTotal }}
      - uses: actions/upload-artifact@v4
        if: always()
        with: { name: blob-report-${{ matrix.shardIndex }}, path: blob-report }

  merge-reports:
    if: ${{ !cancelled() }}     # merge even when shards failed — that's when you need the report
    needs: [test]
    steps:
      - uses: actions/download-artifact@v4
        with: { path: all-blob-reports, pattern: blob-report-*, merge-multiple: true }
      - run: npx playwright merge-reports --reporter html ./all-blob-reports
```

Cache browser binaries in CI — per-shard `playwright install` overhead multiplies by shard count. Rebalance when one shard dominates: split the oversized spec file.

## Level 3: Per-action cost

- Run headless in CI unless a product-specific browser issue requires otherwise.
- Reuse the worker's browser; keep BrowserContexts test-scoped (context creation is cheap; browser launch is not). Never launch browsers manually inside tests; close popups/contexts created outside standard fixtures.
- `waitUntil: 'domcontentloaded'` on `goto` when the test's readiness signal is an element assertion anyway — waiting for `load` (images, fonts, trackers) adds nothing.
- Block heavyweight resources (images, fonts, analytics) at a shared fixture or project level for tests that don't need them. **Exception: visual tests need full rendering** — keep screenshot tests in a separate project with blocking disabled.
- Mock at boundaries the test is not validating (see below).

## Network and external systems

- Mock only at a boundary the test is not intended to validate; keep a smaller set of contract and end-to-end tests against real integrations so mocks can't drift unnoticed.
- Mocked responses must be schema-valid and representative. Never use routing to make an invalid product state appear valid.
- Record which dependencies are mocked in the test title, annotation, or project name — a reader must be able to tell what a green run actually proved.

## Measure — performance is a product metric

Optimizing without measurement is guessing. Track over time, not just per-run:

- Total suite time; p50/p95 test duration; slowest tests and fixtures.
- Setup time separately from scenario time (reveals where "delete work" applies).
- Retry rate and flaky rate — rising flake silently doubles CI cost.
- Use trace viewer on slow tests to see which steps dominate.
- Fail or warn when a test exceeds its agreed budget — but base budgets on the application and the test's value, not arbitrary universal millisecond targets.

Optimize the longest critical path before micro-optimizing locator calls.

## Configuration baseline

Adapt rather than copy — every line here encodes one of the decisions above:

```ts
import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './tests',
  fullyParallel: true, // requires the isolation rules above
  forbidOnly: Boolean(process.env.CI), // a stray test.only silently skips the suite
  retries: process.env.CI ? 2 : 0, // diagnostic evidence, not permission for flake
  workers: process.env.CI ? '50%' : undefined, // tune from measured CI capacity

  reporter: process.env.CI ? 'blob' : [['list'], ['html', { open: 'never' }]],

  expect: { timeout: 5_000 },

  use: {
    baseURL: process.env.E2E_BASE_URL ?? 'http://127.0.0.1:3000',
    trace: 'on-first-retry', // rich diagnostics without taxing green runs
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    actionTimeout: 10_000,
    navigationTimeout: 30_000,
  },

  projects: [
    { name: 'setup', testMatch: /.*\.setup\.ts/ },
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'], storageState: 'playwright/.auth/user.json' },
      dependencies: ['setup'],
    },
  ],

  outputDir: 'test-results',
})
```

Browser matrix by risk, not by default: fast primary-browser coverage on every PR; focused cross-browser smoke on every PR; broader cross-browser on a schedule or release gate. Base the matrix on actual product usage and browser risk.

## Local iteration speed

Developer feedback loops are performance too:

- `npx playwright test --last-failed` reruns only what failed.
- `--repeat-each=10` proves a fix for an intermittent failure.
- `--ui` mode for time-travel debugging instead of console-logging through reruns.
