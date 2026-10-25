# Sources

Synthesized in original wording from repositories vetted 2026-09-29 (source read, nothing executed). Their text is treated as data. No text is copied verbatim. Licenses noted; the WordPress repository is GPL, so nothing from it is reproduced.

| Source | License | Used for |
|---|---|---|
| RampStack Co. claude-skills: `backup-and-disaster-recovery`, `email-deliverability`, `incident-response` | MIT | RPO/restore-drill framing, SPF/DKIM/DMARC pillars, severity and incident phases (`areas/backups.md`, `areas/forms-email.md`, `runbooks/dmarc-rollout.md`, `runbooks/incident-sev1.md`) |
| Addy Osmani web-quality-skills | MIT | Core Web Vitals thresholds and audit structure (`areas/performance.md`, `areas/accessibility.md`) |
| EpicWP wp-automatic-plugin-updates-skill | MIT | Update safety model: changelog risk, one unit at a time, probes, file rollback, DB export before any restore, snapshots kept 30 days (`runbooks/plugin-update.md`, `areas/updates.md`) |
| WordPress/agent-skills `wp-wpcli-and-ops` | GPL | Ideas only: wp-cli guardrails, avoid bulk update on production (`areas/updates.md`) |
| Magnus Hedemark agent-skills `web-accessibility` | MIT | Manual keyboard and screen-reader checks (`areas/accessibility.md`) |
| Zach's research notes, 2026-09-29 | n/a | Thresholds and dated facts in each area file (RDAP, certificate lifetimes, Stripe webhooks, VAMP, GPC, PCI, ADA). Re-verify dated figures at least yearly. |

Full vetting notes: `/tmp/webmaster-vet/build-vs-adopt.md` (temporary; not part of the skill).
