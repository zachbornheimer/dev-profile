# Restore without losing orders

A restore overwrites everything written since the backup: orders, donations, new members, subscription renewals. Subscriptions may then miss a renewal or renew twice. Snapshot the current state first (step 2) so the restore itself can be rolled back.

## Before restoring

1. **Decide if restoring is necessary.** Prefer a targeted fix (rollback one plugin's files, repair one table) when the database is intact.
2. **Export the current DB first** (`wp db export`), even if broken, plus files, stored separately from the backup you will restore.
3. **Pause checkout** (maintenance mode or disable the payment gateway) so no new orders arrive mid-restore. Note the exact pause time.
4. **Export what would be lost**: orders, subscriptions, memberships and new users created after the backup timestamp, exported by hand over wp-cli. With HPOS enabled, use the HPOS-aware export; if switching order storage, run `wp wc hpos sync` first.
5. **List Stripe activity since the backup** (charges, refunds, subscription events) as the source of truth for reconciliation.
6. **Use a DB and files pair from the same moment.** WooCommerce extensions migrate the database; mismatched files and DB break them.

## Restore

7. Restore files and database from the same backup, in staging first if a staging copy exists; otherwise restore in place after step 2.
8. Flush caches; run `wp core verify-checksums`; confirm plugin versions match the DB versions.

## After restoring (replay)

9. Replay the exported orders and users from step 4 that are missing. Match each to its Stripe charge; do not recharge.
10. Subscriptions: check each renewal that fell between the backup and now; avoid a second charge, and manually process any missed renewal. Check on-hold subscriptions and paused memberships.
11. Re-enable checkout; run a Stripe test-mode synthetic order; check the webhook endpoint is receiving events.
12. Confirm scheduled actions (Action Scheduler) are running and not replaying old jobs.
13. Log everything in the change log; tell the client contact (via Zach) which transactions were manually reconciled.

**Browser tests:** when writing or changing Playwright tests for this (synthetic login/checkout, visual regression, axe), load the `world-class-playwright` skill.
