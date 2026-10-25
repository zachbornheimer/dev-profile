/**
 * Timeout policy for the whole suite. Categories, not per-test choices.
 *
 * Local overrides are a lint error; use the escape-hatch syntax with a ticket if
 * one is genuinely unavoidable. Without this, slow tests normalize themselves
 * one 200ms at a time and nobody can point at when it happened.
 */
export const timeout = {
  /** Web-first assertion retry budget. */
  assertion: 5_000,
  /** Page navigation and route transitions. */
  navigation: 15_000,
  /** Eventual consistency in backend systems, via domain wait primitives only. */
  backendConsistency: 30_000,
  /** Whole-test ceiling. Exceeding this is a design problem, not a config one. */
  test: 45_000,
  /** Whole-suite ceiling in CI; past this the suite leaves the pre-merge path. */
  suite: 12 * 60_000,
} as const

/** Per-test duration budget by tag, enforced as a CI gate. */
export const durationBudget = {
  '@smoke': 15_000,
  '@critical': 30_000,
  '@regression': 45_000,
} as const
