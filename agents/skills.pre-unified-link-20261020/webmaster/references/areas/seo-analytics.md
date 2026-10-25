# SEO and analytics

**Check:** No `webmaster` capability measures this yet: report it as unmeasured, never healthy. Intended scope (Search Console API: search analytics, sitemaps, URL inspection; page tags; GA4).

**What is checked**
- `robots.txt` and meta robots: any accidental `noindex` or `Disallow: /` (common after staging copies or theme settings). Sev2.
- Canonicals point at the right URL; sitemap present, valid, and submitted; sitemap URLs return 200.
- Search Console: clicks and impressions trend, coverage errors, manual actions, key URL inspection on home, donate, register.
- GA4 fires exactly once per page (not zero, not twice), and respects consent mode.

**Triage**
- noindex or robots block found: fix right away, then request reindex.
- Traffic drop over 30% month over month: check indexing, redirects, and recent change-log entries first.
- Double-firing GA4: duplicate tag from theme and plugin.

**Needs Zach:** Search Console and GA4 access belongs to the client; back up before changing tags or robots.

**Common misses:** staging noindex shipped to production; canonical pointing to www vs non-www inconsistently; analytics firing before consent.

**Cadence:** robots/noindex daily; Search Console monthly; GA4 tag check monthly.
