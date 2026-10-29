# Method

Mission: evidence, diagnosis, action, verification, prevention. A finding with no next action is incomplete.

## Modes

Choose from the request; say which one you chose in the first line of the report.

- **Investigate:** something is wrong or unclear; find the cause.
- **Audit:** assess an area against thresholds.
- **Remediate:** fix a known problem.
- **Verify:** prove an earlier fix or claim.
- **Operate:** routine cycle, updates, onboarding, offboarding.
- **Incident:** impact now. Order: establish impact, stop damage, restore the critical path, preserve evidence, find root cause, verify recovery, prevent recurrence.

## Critical journeys first

Start from what people must be able to do: sign in, renew, register, donate, contact. Test the journey end to end before area checklists. A broken journey outranks every cosmetic finding.

## Ranking needs-you

Rank by impact class first, then severity, then scope (for example, members affected):

1. Site down, or data exposure/compromise.
2. Money paths: renewals, checkout, payment retry, on-hold members, webhooks. Record only (Zach, 2026-09-30): ordered here for the Records section, never in the numbered needs-you list. See `policies/approvals.md`.
3. Access and security: unexpected admins, debug files, closed plugins with known vulns.
4. Everything else.

Severity labels do not weigh business impact, so never sort by them alone. The digest shows the top 3, then "Also needs you: N more". An `ask` finding is never omitted.

## Tickets

Before fixing, group findings by root cause or owner, then file or update one linear-personal ticket per group (many findings map to one ticket via `{finding_id: ticket}`), and record the `{finding_id: ticket}` mapping in the change log. Fix only what has a ticket; a finding with no ticket waits for one.

**Grouping strategy:** stale admins together, redirect chains together, stray files of one kind together, performance per site, accessibility per site, money records per topic.

**Match existing group tickets first** to avoid duplicates:

1. Search for an existing ticket describing the group's root cause — update it with new evidence instead of filing new.
2. Search by key terms (component, host, error wording) for an older ticket covering the same problem — comment new evidence on it.
3. Check for an older, broader ticket that this group is part of — comment these findings on it.
4. Otherwise, file new. **Stop and re-group if more than 10 new tickets would be created.**
5. Before reusing any ticket, verify it is open or Done (skip Duplicate or Canceled; if Duplicate, follow `duplicateOf` to the canonical ticket).

Additional rules:

- **Every ticket includes the group name or first finding ID** so the next run can match it.
- **Link money-path tickets for the same site** as related issues to establish context.

Reuse the ticket if the same group recurs in a later run; update its body with new evidence and status.

## Retrying network errors

A check that failed on a network error ("fetch failed") is re-run once before it is reported as unmeasured.

## Evidence classes

Label every claim with one: **measured** (a tool recorded it), **observed** (saw it happen), **source-confirmed** (read in code or config), **computed** (derived from measured data), **inferred** (reasoned from other facts), **hypothesis** (untested guess).

Never:

- promote a hypothesis to fact;
- promote source-confirmed to runtime-verified;
- treat an axe scan as WCAG conformance;
- treat one lab run as real-user performance;
- treat a tool failure as a site failure (report `error`, not `fail`);
- treat unmeasured as healthy.

## Status vocabulary

Per check: `pass | warn | fail | unmeasured | error`.

Coverage ledger, per area or journey: `TESTED_HEALTHY | TESTED_FINDINGS | PARTIAL | UNMEASURED | NOT_APPLICABLE | BLOCKED`. Every area appears in the ledger. No numeric health scores.

## Finding shape

| Field          | Content                                              |
| -------------- | ---------------------------------------------------- |
| What           | The problem in one sentence                          |
| Where          | URL, page, component, setting                        |
| Evidence       | The proof, with its class                            |
| Impact         | Who is affected and how                              |
| Cause          | Root cause, or "unknown"                             |
| Action         | What to do                                           |
| Implementation | The concrete steps or plan reference                 |
| Verification   | The check that proves it worked (see below)          |
| Prevention     | What stops it recurring                              |
| Severity       | Critical / High / Medium / Low, by impact not effort |
| Confidence     | High / Medium / Low; low means ask                   |

Do not invent effort estimates or owners. One component bug is one finding with its scope, not 47 findings.

## Remediation loop

1. Baseline the failure. 2. Confirm the cause. 3. Make the smallest change. 4. Run checks. 5. Replay the ORIGINAL failure. 6. Compare to the baseline.

A code change is not proof of a runtime fix.

## High-risk changes

DNS, registrar, auth/authz, production data, destructive migrations, bulk deletes, redirect maps, canonicals, robots/noindex, HSTS preload, CSP enforcement, backups, billing, user data.

Each needs: change, expected effect, verification, rollback. And a backup first (`policies/approvals.md`). Use a mounted capability's remedy where one exists, else SSH/wp-cli. No exceptions by tier.

## Verification by problem type

| Problem            | Verify by                                                                |
| ------------------ | ------------------------------------------------------------------------ |
| Broken link        | Re-request the URL; re-crawl the referring pages                         |
| User journey       | Repeat the task as a user (Playwright, test mode for payments)           |
| Header or redirect | Inspect the production response                                          |
| Backup             | Controlled restore to a scratch target                                   |
| Monitoring         | Simulate the failure; confirm the alert path fires                       |
| Email              | Send and receive a real message; check SPF/DKIM/DMARC results in headers |
| Performance        | Repeat measurement; note lab vs field                                    |

"Looks correct" is not verification.

## Output shape

1. Mode, then the most important problems and the first action.
2. Actions table: Priority | Problem | Action | Why | Verify.
3. Significant findings, in the finding shape.
4. Coverage ledger.

The monthly digest stays one page (`templates/monthly-digest.md`).
