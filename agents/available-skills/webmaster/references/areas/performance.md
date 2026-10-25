# Performance

**Check:** No mounted capability measures this yet: report it as unmeasured, never healthy. Intended scope (CrUX field data, server timing, autoload, Action Scheduler, DB growth).

## Thresholds (field data, p75)
- LCP at most 2.5s, INP at most 200ms, CLS at most 0.1, from the CrUX API. Lab scores (Lighthouse) are diagnostic only. Low-traffic sites may have no CrUX data; say so, don't invent.
- Autoload options total over 800KB: finding.
- Action Scheduler past-due actions: warn above 50, ticket above 500 or oldest past-due more than 24h.
- Admin and uncached TTFB: warn above 800ms.
- Database table growth: any table growing over 25% month over month, or `wp_options`, `postmeta`, `actionscheduler_logs` unusually large.

## Triage
- LCP: usually the hero image (size, format, priority, lazy-loading mistakes).
- INP/CLS: third-party scripts, late-loading fonts or embeds, unsized images.
- Autoload: find the plugin that owns the biggest options; set autoload off or clean expired data.
- Action Scheduler backlog: check WP-Cron/real cron, failed actions, a plugin creating runaway jobs.

**Backup rule applies to:** DB cleanup beyond expired transients; caching or CDN changes; plugin removal.

**Common misses:** optimizing lab scores while field data is fine (or the reverse); measuring a logged-in page; a caching plugin caching checkout or member pages.

**Cadence:** field data monthly; autoload and Action Scheduler weekly.
