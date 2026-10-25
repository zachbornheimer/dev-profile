# Production changes: back up first

The only rule: **back up before changing prod, so it can be rolled back.** No plan approval, no per-tier gate.

1. **Back up.** Copy the files to the site profile's `host.backup_root` (WP Engine: `sites/<install>/_wpeprivate/webmaster-backups/<date>-<ticket>/`; the SSH home dir is ephemeral), `wp db export` for DB changes, or take a host backup point.
2. **Change.** Changes `webmaster` does not automate yet are done directly over SSH/wp-cli.
3. **Verify.** Match the verification to the problem (`references/method.md`).
4. **Report.** Backup location and rollback command go in the change log entry and the digest. The digest reports what changed, it does not ask permission.

A database restore overwrites newer writes; follow `runbooks/restore-without-losing-orders.md`.

## Money paths: record only (until Zach decides)

Zach, 2026-09-30: "I'm not exactly sure what should happen yet with money stuff, so for now, we should just make records." This is record only. Money paths are subscriptions, renewals, on-hold members, payment retry, checkout, Stripe/webhooks, memberships sync, dues and pricing.

- Money-path findings get tickets (match existing tickets first) and appear in the digest under "Records (money paths, no action)".
- They are never placed in the numbered needs-you list.
- They are never turned into a plan, and never get a proposed fix, email to members, setting change or apply step.
- The agent may describe what it observed and how it changed since the last run, and nothing more.
