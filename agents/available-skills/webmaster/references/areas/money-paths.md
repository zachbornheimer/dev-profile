# Money paths

Donation, registration, checkout, subscriptions, memberships.

**Check:** subscription states, retry config, Action Scheduler backlog and memberships sync via wp-cli; Stripe webhook health and dispute rate via the Stripe dashboard (read-only); synthetic checkout in Stripe test mode (finding IDs are `site:commerce:kind:subject`).

## Facts

- An **on-hold** subscription means the renewal failed or the subscription was paused. Count and age of on-hold subscriptions is the leading indicator.
- The Subscriptions **retry system is opt-in** (default 5 retries at 12h, 12h, 24h, 48h, 72h). If it is off, failed renewals go straight to on-hold; confirm the setting.
- **Stripe disables a webhook endpoint after 3 days of failing deliveries.** Alert on any failure, not just disablement.
- Dispute rate: 0.75% is the general concern line; 1.5% is Visa's VAMP line (as of April 2026). Page-worthy well before either.
- Memberships and subscriptions sync: an on-hold subscription pauses the membership, so a renewal problem shows up as "members locked out".
- Synthetic tests use Stripe **test mode, admin-only**, never real cards or real customer orders.

## Triage

- Webhook failing: Sev1 if payments are not creating orders; fix endpoint, resend failed events, reconcile orders against Stripe charges.
- On-hold spike: check gateway errors, expired cards, retry setting, Action Scheduler.
- Dispute rate rising: list disputes, check descriptor clarity and refund policy; report to Zach.
- Synthetic checkout fails: Sev1.

**Record only (Zach, 2026-09-30):** until Zach decides, findings here are ticketed and listed as records in the digest. No plan, proposed fix, member email, setting change or apply step. See `policies/approvals.md`.

**Needs Zach:** anything in Stripe (client owns it); refunds; changing retry or gateway settings.

**Common misses:** a webhook silently disabled; test-mode keys live in production or the reverse; checkout page cached; subscription renewals stuck behind past-due scheduled actions.

**Cadence:** synthetic test and webhook check daily; subscription states weekly; disputes monthly.

**Browser tests:** when writing or changing Playwright tests for this (synthetic login/checkout, visual regression, axe), load the `world-class-playwright` skill.
