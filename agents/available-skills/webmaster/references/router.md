# Router

Map a plain-language problem to a mode, then to the runbook or area file. Pick the row for the symptom; if two match, the higher one in "Critical journeys" wins.

## Sites

| Name | Site | Tier | Notes |
|---|---|---|---|
| bpp | bestplanpro.com | business | SAH WooCommerce, AWS ECS, no SSH. |
| isjac | isjac.org | client | Membership, renewals, events, donations. Client owns all accounts. |
| zbm | zachbornheimermusic.com | personal | See canary note below. |
| zysys | zysys.org | business | Minimal site. |

**zbm canary (do not fix).** `www.zachbornheimermusic.com` returning 404 is a known, deliberate canary. Report it as "known canary, unchanged". Never propose or apply a fix unless Zach says so in this conversation. If it changes (no longer 404), report that as a finding.

Ask which site only when the request could apply to more than one and the text gives no clue.

## Site notes

**isjac contacts and workflow.** Primary contact is Steve (Managing Director, not yet public; on the site he is listed as Production Assistant). Email is primary, text for emergencies. Check-ins are bi-weekly and flexible. Steve BCCs Zach on external comms.

## Full router

| What Zach says | Mode | Do |
|---|---|---|
| "check <site>", "monthly check", "site health" | Operate | Operate loop (SKILL.md), steps 1-2 |
| "is <site> up", "site is slow to load" | Investigate | probe uptime from two vantage points yourself; `areas/uptime.md` (then `areas/performance.md` if slow) |
| Site down, hacked, checkout broken, error on every page | Incident | `runbooks/incident-sev1.md` |
| "update plugins/core", "is X safe to update" | Operate | `runbooks/plugin-update.md`; `areas/updates.md` |
| "backup ok?", "restore", "lost data" | Verify / Incident | `areas/backups.md`; `runbooks/restore-without-losing-orders.md` |
| Member can't log in, username or email change, locked out | Remediate | `runbooks/member-account-change.md`; `areas/access.md` |
| Admin leaving or joining | Operate | `runbooks/admin-offboarding.md` |
| Emails not arriving, form submissions missing, DMARC | Investigate | `areas/forms-email.md`; `runbooks/dmarc-rollout.md` |
| Domain, DNS, certificate, "not secure" warning, www link broken | Investigate | `areas/domains-dns-tls.md` (zbm: read the canary note first) |
| Renewals, Stripe, checkout, memberships, donations failing | Investigate | `areas/money-paths.md` |
| Slow, Core Web Vitals, Lighthouse | Audit | `areas/performance.md` |
| Vulnerability, malware, security headers, suspicious admin | Investigate / Incident | `areas/security.md` |
| Broken links, stale events, page looks different | Investigate | `areas/content-pages.md` |
| Search Console, GA4, noindex, "not on Google" | Investigate | `areas/seo-analytics.md` |
| Cookie banner, privacy policy, PCI | Audit | `areas/privacy.md` |
| Accessibility complaint or audit | Audit | `areas/accessibility.md` |
| "did the fix work", "verify X" | Verify | `references/method.md` verification table; replay the original failure |
| New site | Operate | `runbooks/new-site-onboarding.md` |
| Ending or transferring engagement | Operate | `runbooks/handoff-pack.md` |
| Meeting notes / email pasted | Operate | `runbooks/client-notes-intake.md` |
| Backup rule, how fast | (answer) | `policies/approvals.md`, `policies/severity-sla.md` |
