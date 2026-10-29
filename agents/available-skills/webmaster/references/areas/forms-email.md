# Forms and email

**Check:** SPF/DKIM/DMARC from DNS records, Mailgun status and suppressions via the Mailgun API (read-only), and the weekly seed-inbox synthetic form test you send and verify (finding IDs are `site:mail:kind:subject`).

## Facts

- DKIM is what aligns Mailgun mail for DMARC. Confirm DKIM is enabled and aligned.
- DMARC rollout: read `rua` reports for 2-4 weeks at `p=none`, then quarantine, then reject (`runbooks/dmarc-rollout.md`).
- Complaint rate under 0.1%; never let it reach 0.3%.

## Thresholds

- Weekly seed-inbox synthetic test per form: submission arrives in the seed inbox within 5 minutes, not in spam, correct recipient. Failure: Sev2.
- Mailgun: bounces above 2% or new suppressions for real members: finding. Check the suppression list when "I never got the email".
- SPF over 10 lookups or more than one SPF record: finding.

## Triage

- Form not delivering: check the form plugin log, site mail transport, Mailgun log, suppression list, DNS records, spam placement.
- Password-reset emails missing: same path.
- Spoofing reports: DMARC state.

**Backup rule applies to:** DNS changes; DMARC policy steps; changing mail provider.

**Common misses:** forms that "succeed" in the UI but the email fails; a form notification going to a departed person; a captcha or anti-spam plugin blocking real users.

**Cadence:** synthetic tests weekly; DMARC reports weekly during rollout, monthly after.
