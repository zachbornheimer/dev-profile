# Domains, DNS, TLS

**Check:** DNS records yourself (dig or DNS-over-HTTPS) and TLS expiry from the served certificate; registrar and domain expiry via RDAP where reachable, otherwise unmeasured.

## Thresholds

- Domain expiry via RDAP: warn at 60 days, page at 14. Also check registrar lock and auto-renew (off is a finding).
- Certificate: the maximum lifetime is 200 days from 2026-03-15, 100 days in 2027, 47 days in 2029. Warn at 21 days remaining, page at 7, and alert on any renewal failure. Short lifetimes make automated renewal mandatory.
- Dangling CNAMEs pointing at deprovisioned services (subdomain takeover): finding, Sev2.
- DNS drift: records are snapshotted; any change not in the change log is a finding.
- CAA present and correct; DNSSEC status recorded (advisory).

## Triage

- Expiring domain: the client owns the registrar; Zach tells the client contact to renew, with a date.
- Cert renewal failing: check the host's ACME job, DNS/HTTP validation, CAA blocking the CA.
- Dangling record: remove after confirming nothing uses it.
- Unexpected DNS change: treat as possible hijack; confirm with registrar logs.

**DNS or registrar changes:** export the current records first (backup rule).

**Common misses:** subdomains with separate certs; expiry of a domain the client owns outside our list; auto-renew card expired.

**Cadence:** daily cert and expiry check; DNS snapshot weekly.
