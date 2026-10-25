# Severity and response targets

Best-effort, business hours (Mon-Fri, Zach's local time). These fit a client paying about $500 per quarter. They are targets, not contract guarantees, and the client's scope document should say so.

| Sev | Meaning | Examples | Acknowledge | Mitigate |
|---|---|---|---|---|
| 1 | Site down, checkout or donations broken, active compromise, data loss | Confirmed outage; Stripe payments failing; malware found | Same day, including evenings when confirmed by two vantage points | Same day, best effort |
| 2 | Major feature broken, no workaround | Members cannot log in; forms not delivering; renewals failing | 1 business day | 2 business days |
| 3 | Degraded or partial, workaround exists | Slow pages, one broken form, cert under 21 days | 2 business days | Next monthly session or 10 business days |
| 4 | Cosmetic or advisory | Minor visual issue, info findings | Digest | Backlog |

## Security patches

Actively exploited or critical vulnerability in an installed plugin: assess within 24 hours, patched or mitigated (disable, virtual patch, or WAF rule) within 24-72 hours. Non-critical: next monthly cycle.

## Fix-size cap

About 5 hours per issue inside the retainer. Past that, stop, write a short estimate, and ask Zach before continuing.

## Paging rule

Page only on confirmed-down (second vantage point agrees, homelab connectivity checked first) or Sev1. Warnings go to the digest.
