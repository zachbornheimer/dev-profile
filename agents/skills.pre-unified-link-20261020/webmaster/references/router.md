# Router

Map a plain-language problem to a mode, then to the runbook or area file. Pick the row for the symptom; if two match, the higher one in "Critical journeys" wins.

## Sites

| Name | Site | Tier | Notes |
|---|---|---|---|
| bpp | bestplanpro.com | business | SAH WooCommerce, AWS ECS, no SSH; changes via ECS one-off tasks. Tickets: linear-sah. |
| isjac | isjac.org | client | Membership, renewals, events, donations. Client owns all accounts. |
| zbm | zachbornheimermusic.com | personal | See canary note below. |
| zysys | zysys.org | business | Minimal site. |

**zbm canary (do not fix).** `www.zachbornheimermusic.com` returning 404 is a known, deliberate canary. Report it as "known canary, unchanged". Never propose or apply a fix unless Zach says so in this conversation. If it changes (no longer 404), report that as a finding.

Ask which site only when the request could apply to more than one and the text gives no clue.

## Site notes

**isjac contacts and workflow.** Primary contact is Steve (Managing Director, not yet public; on the site he is listed as Production Assistant). Email is primary, text for emergencies. Check-ins are bi-weekly and flexible. Steve BCCs Zach on external comms.

**isjac code fixes (headers, redirects, theme/plugin code) ship as isjac-site PRs, not SSH edits.** Repo `ZAB-AI-LLC/isjac-site` (`~/Developer/ZAB-AI/isjac-site`); merge to main deploys to WP Engine via `deploy-wpe.yml`, whose last step `scripts/smoke_live.py` checks key URLs, `/store`→`/shop` and the security headers live. The repo has no PR checks, so `wt pr-auto` needs dev-profile e84333c or newer (older watchers report "CI failed" on zero checks). isjac DNS is GoDaddy (client-owned), not Terraform.

**bpp fixes: wp-cli through ECS tasks, everything else as infra PRs.** bpp has no SSH. Its profile has `host.transport: ecs`: `webmaster fix bpp` / `apply` run their wp-cli remedies (DB-level, e.g. option changes) in a one-off task of `bpp-wordpress-prod` (cluster `bpp-wordpress-cluster`, us-west-2, `AWS_PROFILE=sah`), backing up first to `s3://bpp-wordpress-deployment/webmaster-backups/<dir>.tgz` (the change record names it and the undo). Each task takes about two minutes. Checks stay public-HTTP. `webmaster wp bpp <read>` runs one read-only wp-cli command (`core version`, `option get <name>`, `plugin list`...) for evidence; never run ad-hoc `aws ecs run-task` or ECS Exec against prod (ECS Exec is not connected: the task role lacks ssmmessages). File changes (plugins, themes, core, stray files) are code: `fix` routes them to the worklist naming `Software-Automation-Holdings-LLC/infra-bpp` `wordpress-app/` (composer.json), because the image is rebuilt from it. Edge, DNS, header and TLS fixes go in `Software-Automation-Holdings-LLC/infra` (`environments/prod/wordpress/`). Both ship via a `wt` worktree and `wt pr-auto`; `opentofu.yml` applies infra on merge to main, and the PR's git revert is the rollback. Check main CI first (`gh run list --branch main --workflow ci.yml`): a red main blocks every PR. All bpp tickets live in linear-sah (team Development, project Best Plan Pro); the old ZYS bpp tickets were moved there on 2026-10-14 (SAH-10797..10805) and canceled in ZYS. `bpp:availability:uptime-low` counts a failed alias (www) as site down, so read the outages table before calling the apex down.

## Full router

| What Zach says | Mode | Do |
|---|---|---|
| "check <site>", "monthly check", "site health" | Operate | Operate loop (SKILL.md), steps 1-2 |
| "is <site> up", "site is slow to load" | Investigate | `webmaster uptime <site>`; `areas/uptime.md` (then `areas/performance.md` if slow) |
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
