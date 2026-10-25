# Security

**Check:** everything under "What is checked" below, run by you — wp-cli over the profile's transport for checksums and users, HTTP probes for exposure and headers, DNS/TLS reads (finding IDs are `site:security:kind:subject`).

## What is checked
- `wp core verify-checksums` (core files unchanged).
- PHP files inside `uploads/` (finding; usually a compromise or bad plugin).
- `debug.log` and backup archives reachable by URL.
- `xmlrpc.php` enabled without need; REST/author user enumeration; login page exposure.
- Security headers (HSTS, X-Content-Type-Options, frame protections, referrer policy; CSP is advisory).
- `DISALLOW_FILE_EDIT` set; file permissions; unknown admin users; PHP version.
- Known vulnerabilities in installed plugin and theme versions. Free sources: the Wordfence Intelligence feed (free, no auth) is primary; WPScan free tier allows 25 requests a day (use for spot checks); Patchstack's API is paid and not assumed.

## Triage
- Vulnerability with a fixed version: update (`updates`); actively exploited: 24-72h target.
- Vulnerability with no fix: disable, restrict, or replace, after a backup.
- PHP in uploads, unknown admin, checksum failure: treat as compromise, `runbooks/incident-sev1.md`.
- Header or xmlrpc findings: ticket or auto after backup.

**Tell Zach:** any suspected compromise. Disabling a plugin and credential rotation follow the backup rule.

**Common misses:** hosting-level exposure (directory listing, `.git`, `.env`, backup zips); stale admin accounts; treating a clean checksum run as proof of no compromise.

**Cadence:** vulnerability feed weekly (daily for actively exploited alerts); full security audit monthly.
