# Tiers

required version: 0.1.0 (the preflight compares `webmaster --version` against this line).

| | client | business | personal |
|---|---|---|---|
| Example | ISJAC | SAH sites | Zach's own |
| Who owns accounts | The client | SAH | Zach |
| Production changes | Back up first, change, verify, report | Same | Same |
| Cadence | Monthly cycle, monthly digest, quarterly board report | Monthly cycle, digest to Zach only | Quarterly cycle |
| Tickets | linear-personal, team Zysys, project ISJAC | linear-sah (bpp: team Development, project Best Plan Pro) | none required |
| Paging | Confirmed-down and Sev1 only | Confirmed-down and Sev1 | Confirmed-down only |
| Change log + site bible | Required | Required | Optional |

**Client tier scope** (the one-page scope and SLA the client signed): monthly session, weekly light check, best-effort response in business hours (see `severity-sla.md`), fix-size cap about 5 hours per issue; larger work is quoted separately.

The client owns the registrar, host, Stripe, mail provider and DNS. Zach holds delegated access in the client's own 1Password vault (one vault per client).
