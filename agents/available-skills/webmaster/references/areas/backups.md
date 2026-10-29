# Backups

**Check:** No mounted capability measures this yet: report it as unmeasured, never healthy. Intended scope (age, size delta, offsite presence, heartbeat, restore-drill date).

**Rule 3-2-1:** three copies, two media, one offsite. The host's own backup counts as one copy, not the offsite one. The offsite copy must use separate credentials, so a compromise of the site cannot delete it.

## Thresholds

- Newest backup older than 26 hours (daily schedule): finding. Older than 72 hours: Sev2.
- Size drops more than 30% against the trailing median: finding (empty or partial dump).
- Monthly: import the latest DB dump into a temporary database and count key tables (users, posts, orders).
- Quarterly: full restore drill to a scratch environment; record the date and result. No drill in 100 days: finding.
- Offsite copy missing or unreadable with the separate credentials: Sev2.

## Triage

- Missed backup: check the heartbeat, disk space, host quota, and the backup plugin log; fix, then confirm the next run.
- Restore drill fails: Sev2, fix before anything else changes on the site.

**Restores overwrite orders placed since the backup, and subscriptions may miss or double renewals.** See `runbooks/restore-without-losing-orders.md`. Before switching to HPOS order storage, run `wp wc hpos sync`.

**Restores and backup-destination changes:** snapshot the current state first, then follow the backup rule.

**Common misses:** database and files from different moments; backups stored under the web root; backup succeeded but is empty; nobody has ever restored one.
