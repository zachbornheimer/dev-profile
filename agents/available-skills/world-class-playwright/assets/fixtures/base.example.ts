/**
 * The base fixture — the ONLY module permitted to import @playwright/test.
 *
 * Every spec comes through here, which makes this the single surface for
 * identity, isolation, data namespaces, API clients, cleanup, clock, feature
 * flags, and diagnostics. Policy changes are one edit rather than N.
 *
 * Skeleton: adapt the domain types and client construction. Keep the shape.
 */
import { test as base, expect as baseExpect } from '@playwright/test'
import { timeout } from '../timeouts'
import * as domainMatchers from '../../assertions'

type Fixtures = {
  /** Collision-free across workers, parallel slots and repeats. Never Date.now(). */
  unique: (prefix: string) => string
  /** An isolated tenant/account for this test. Never shared, never fixed. */
  tenant: { id: string; name: string }
  /** Authenticated page for a named role; storage state reused per worker. */
  authedPage: import('@playwright/test').Page
  /** Typed API client for setup, cleanup and backend assertions. */
  api: unknown
  /** Register cleanup here; runs idempotently even if setup half-completed. */
  cleanup: (fn: () => Promise<void>) => void
}

export const test = base.extend<Fixtures>({
  unique: async ({}, use, testInfo) => {
    let n = 0
    await use((prefix) => `${prefix}-w${testInfo.workerIndex}-p${testInfo.parallelIndex}-${++n}`)
  },

  tenant: async ({ api, unique }, use) => {
    const tenant = { id: unique('tenant'), name: unique('Acme') }
    // await (api as OrdersApi).createTenant(tenant);
    await use(tenant)
    // cleanup is registered below so it survives a mid-test failure
  },

  cleanup: async ({}, use) => {
    const tasks: Array<() => Promise<void>> = []
    await use((fn) => tasks.push(fn))
    // Idempotent, tolerant of partial setup, and never masks the test's own error.
    for (const task of tasks.reverse()) {
      await task().catch((error) => {
        console.error('cleanup failed (non-fatal):', error)
      })
    }
  },

  api: async ({}, use) => {
    await use({} /* new OrdersApi({ baseURL: process.env.API_URL }) */)
  },

  authedPage: async ({ page }, use) => {
    await use(page)
  },

  /**
   * Diagnostics are infrastructure, not the author's responsibility.
   * Auto-fixture: runs for every test without being requested.
   */
  page: async ({ page }, use, testInfo) => {
    const consoleErrors: string[] = []
    const failedRequests: string[] = []

    page.on('console', (msg) => {
      if (msg.type() === 'error') consoleErrors.push(msg.text())
    })
    page.on('requestfailed', (req) => {
      failedRequests.push(`${req.method()} ${req.url()} — ${req.failure()?.errorText}`)
    })

    page.setDefaultTimeout(timeout.assertion)
    page.setDefaultNavigationTimeout(timeout.navigation)

    await use(page)

    if (testInfo.status !== testInfo.expectedStatus) {
      await testInfo.attach('final-url', { body: page.url() })
      if (consoleErrors.length) {
        await testInfo.attach('console-errors', { body: consoleErrors.join('\n') })
      }
      if (failedRequests.length) {
        await testInfo.attach('failed-requests', { body: failedRequests.join('\n') })
      }
    }
  },
})

export const expect = baseExpect.extend(domainMatchers)
