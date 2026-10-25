# Handoff pack

The client owns the registrar, host, Stripe and mail accounts at all times. This pack lets them (or a successor) run without Zach.

Prepare at onboarding, refresh yearly and on engagement end.

1. **Account ownership table**: registrar, DNS host, web host, Stripe, Mailgun, mailing list, Google properties, 1Password. For each: owner of record (the client organization), admin contacts, where billing goes, renewal dates. Confirm the registrar lock and auto-renew.
2. **Credential escrow**: one 1Password vault per client. At least two client-side people have owner access to the vault and can recover it. Zach holds delegated, revocable access.
3. **Site bible** (single document): what the site is, plugins and why each exists, protected plugins, payment and membership flows, custom code (`isjac-core`), scheduled jobs, backup locations and restore steps, DNS records, mail senders, known quirks, the contacts and the scope/SLA.
4. **Change log** export (append-only) and the last two quarterly board reports.
5. **Restore proof**: date and result of the last restore drill.
6. **Exit steps**: revoke Zach's access, rotate shared secrets (`admin-offboarding.md`), transfer any accounts Zach holds in his own name (there should be none).
