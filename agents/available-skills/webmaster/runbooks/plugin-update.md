# Plugin update

Order: backup, core, then plugins one at a time (WooCommerce first, then its extensions), then themes. Never `update --all` on production.

1. **Inventory.** List available core, plugin and theme updates with wp-cli over the profile's transport, then write the update plan yourself from it (order, risk, backups). Note closed/premium plugins: these show through the wp.org API only if public; `wp plugin verify-checksums` does not cover premium plugins, so check their version from the vendor.
2. **Risk read.** Judge changelog risk yourself. Flags: database migration, major version, removed features, PHP version bump, age of last release, abandoned plugin. Low confidence goes in the digest as a question and the update waits.
3. **Classify.** DB-migrating plugins need a DB export as well as a file copy. Every tier follows the backup rule (`policies/approvals.md`).
4. **Digest item.** One line per update: plugin, from -> to, risk, why now, backup location, rollback command. Security fixes say so.
5. **Backup.** Confirm a fresh full backup (DB and files, same moment, offsite copy exists) before touching anything.
6. **Apply one unit at a time.** Update over SSH/wp-cli under the backup rule: snapshot the plugin directory, update, wait for the site to settle, re-probe (front page, login, checkout page, a form, error log). Fail: roll back the file snapshot automatically. If the plugin migrated the DB, a file rollback is not enough; restore the same-moment DB export and files.
7. **Core last** with its own snapshot. PHP 8.1 reached end of life on 2025-12-31; a site still on it needs a PHP upgrade plan.
8. **Never** use real customer orders or send real email as a test. Use Stripe test mode admin-only and the seed inbox.
9. **Record** each unit in the change log; keep snapshots at least 30 days, outside the web root.
