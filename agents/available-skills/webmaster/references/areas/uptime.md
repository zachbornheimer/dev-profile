# Uptime

**Check:** probes from the homelab and one outside vantage point with keyword match, plus heartbeats — run by you (cron, a script, or mounted monitoring) and read back (finding IDs are `site:uptime:kind:subject`).

## Thresholds
- HTTP 200 alone is not up. The check requires an expected keyword (a phrase from the real page), because error pages and maintenance screens return 200.
- Confirmed-down = two vantage points fail within the same window. Before believing a failure, the homelab checks its own connectivity.
- Response time: warn if p95 exceeds 3s over a day.
- Heartbeat (dead-man switch): cron, backup job, and Action Scheduler each ping a heartbeat URL; a missed ping is a finding.

## Triage
- One vantage fails: warning, digest only. Recheck in 5 minutes.
- Confirmed down: page Zach, open `runbooks/incident-sev1.md`.
- Keyword missing but 200: treat as down (error page, hacked page, or empty theme).
- Missed heartbeat: cron or backup broke silently; route to `backups` or `performance` (Action Scheduler).

**Tell Zach:** any page. Restarts and rollbacks follow the backup rule.

**Common misses:** checking only the front page (login and checkout can be down alone); monitoring the CDN instead of the origin; homelab outage read as site outage; maintenance mode left on after an update.

**Cadence:** probes every 1-5 minutes; heartbeats per job schedule; uptime percent in the monthly digest.
