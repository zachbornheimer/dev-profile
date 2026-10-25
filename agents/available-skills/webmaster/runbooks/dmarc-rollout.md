# DMARC rollout

Goal: reject spoofed mail from the client's domain without blocking real mail (Mailgun forms, site mail, newsletters).

DNS changes follow the backup rule: export the current records first. DNS is at the client's registrar or DNS host; Zach uses delegated access.

1. **Inventory senders**: everything that sends as the domain (Mailgun, the mailing list, Google Workspace, the CRM, Stripe receipts).
2. **SPF**: one record only; watch the 10-lookup limit. **DKIM**: enable for each sender. DKIM is what aligns Mailgun mail for DMARC (its default envelope domain does not align for SPF), so confirm DKIM is on and aligned.
3. **Publish `p=none`** with an `rua` address that reaches a report reader. Do nothing else for 2-4 weeks.
4. **Read the rua reports** weekly. Every legitimate source must pass DKIM or SPF with alignment. Fix or add senders until real mail passes.
5. **Move to `p=quarantine`** (start with `pct=25`, then 100) for 2 weeks; watch for legitimate mail landing in spam and for complaints.
6. **Move to `p=reject`** when reports are clean. Keep watching monthly.
7. Watch reputation: complaint rate under 0.1%, never 0.3%; Mailgun bounces and suppressions.
8. Each step is a change-log entry with the exact record before and after. Snapshot DNS records first so drift is detectable.
