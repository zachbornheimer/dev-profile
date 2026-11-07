---
name: e2e
description: >
  Three-tier web, browser, and end-to-end testing hierarchy: Firecrawl MCP or
  read(url)/fetch for scraping public pages, e2e (https://e2e.tester.army) for
  E2E suites, exploratory charters, and UI verification, and Bun 1.4+
  Bun.WebView for lightweight native headless checks. Use when writing or
  running E2E tests, verifying UI flows, exploring an app for bugs, or choosing
  between scraping, E2E testing, and lightweight browser automation.
---

# Web, Browser & E2E Testing Hierarchy

Choose the lowest-friction tier that matches the task. Never reach for raw Playwright to scrape a page, and never hand-roll brittle selector scripts when `e2e` or `Bun.WebView` fits.

| Need | Tier | Tooling |
| --- | --- | --- |
| Read, search, or map public web pages | **1. Scraping / Reading** | **Firecrawl MCP** (`firecrawl/firecrawl_scrape`, `firecrawl/firecrawl_search`, `firecrawl/firecrawl_map`) or `read(url)` / `fetch` — **never Playwright** |
| E2E test suites, UI verification, bug bashes, live app inspection | **2. E2E Testing & Exploration (`e2e.tester.army`)** | `bunx e2e init --yes`, `bunx e2e run`, `bunx e2e explore '<charter>'`, `e2e mcp` |
| Fast local one-off headless browser check in a script | **3. Native Script Automation (Bun 1.4+)** | Built-in `Bun.WebView` (zero external Playwright dependencies) |

---

## Tier 1: Scraping & Reading Public Pages

When the goal is to extract markdown, inspect documentation, search a site, or map URLs:

1. **Single known URL:** Use `read(url)` / `fetch`, or `firecrawl/firecrawl_scrape` when JS rendering is required.
2. **Site discovery / URL inventory:** Use `firecrawl/firecrawl_map`.
3. **Targeted search across web pages:** Use `firecrawl/firecrawl_search`.

**Rule:** Never launch Playwright, Chromium, or a browser test runner just to read or scrape a public webpage.

---

## Tier 2: E2E Testing, Exploration & UI Verification (`https://e2e.tester.army`)

Use [`e2e`](https://e2e.tester.army) for end-to-end tests, interactive UI verification, and exploratory bug bashes across web and mobile.

### Core Commands

```bash
# Bootstrap e2e non-interactively (writes e2e.config.ts, example test, skill, and MCP config)
bunx e2e init --yes

# Run the suite (or scope to one test line with a fast action timeout while iterating)
bunx e2e run
bunx e2e run tests/checkout.e2e.ts:3 --action-timeout 5000

# Verify live agent execution once the test is green
bunx e2e run tests/checkout.e2e.ts:3 --no-cache

# Explore a flow without writing a test file first (scouting / bug bash)
bunx e2e explore 'Explore checkout like a first-time buyer and report anything off'

# Start or inspect via the e2e MCP server for live session observation and locator checks
e2e mcp
```

### Authoring Pattern: Atomic Goals + Deterministic Verification (`agent.act` + `expect`)

Pair each `agent.act('<atomic goal>')` with a deterministic `expect(screen.getByRole(...))` (or `getByLabel` / `getByTestId`) check:

```ts
import { test, expect } from 'e2e';

test('a member upgrades to Pro', async ({ app, agent, screen }) => {
  await app.open('/settings/billing');

  await agent.act('upgrade the workspace to the Pro plan');
  await expect(screen.getByRole('status')).toContainText('Pro');
});
```

- **Zero-model-call cache replay (`.e2e/cache/`):** Once a step's subsequent `expect(...)` verification check passes, `e2e` records the verified actions into `.e2e/cache/`. Future runs deterministically replay those recorded actions with **zero model calls**, checking that each step produces the same screen effect and handing back to the live agent only if the UI changed. Commit `.e2e/cache/` when you want CI to replay recordings deterministically.
- **No sleeps:** Locators poll, actions wait for targets, and `expect` retries until timeout. Never insert `setTimeout` or fixed sleeps.
- **Live locator verification (`e2e mcp`):** Use `e2e mcp` to open a live session on the app, inspect the semantic tree, and test locators with `locate` before committing them to a test file.

### Debugging Failures with `trace.md`

Every failed, timed-out, or flaky test writes a markdown trace page at:

```text
.e2e/results/<test>/trace.md
```

- **Read `.e2e/results/<test>/trace.md` first** (prefer it over raw `.e2e/report.json` when diagnosing a test failure).
- `trace.md` contains the exact failing line, every executed step, the node each action hit, the values polled by `expect`, the cache replay decision, console errors, uncaught exceptions, failed 4xx/5xx network requests, the agent's last turns, and the screenshot + semantic tree at failure.
- For model-level debugging, run with `--debug` (prints step timing/token/cost table) or `--ai-trace --no-cache`.

---

## Tier 3: Lightweight Native Script Automation in Bun 1.4+ (`Bun.WebView`)

When you only need a fast, self-contained local headless browser check inside a Bun script or `eval` cell — without standing up a full test suite or installing external Playwright packages — use Bun 1.4's built-in `Bun.WebView`:

```ts
// Lightweight native headless check in Bun 1.4+ without external Playwright deps
const view = new Bun.WebView({ headless: true, width: 1280, height: 720 });
await view.navigate('http://127.0.0.1:3000/health');
const title = await view.evaluate('document.title');
```

Use `Bun.WebView` for quick local smoke probes or single-script DOM assertions; graduate to Tier 2 (`e2e`) as soon as you need durable regression tests, cached agent steps, trace artifacts, or CI reporting.
