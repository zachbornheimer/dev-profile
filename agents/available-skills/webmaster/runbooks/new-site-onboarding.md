# New site onboarding

1. **Profile.** Create `sites/<site>.yaml` (copy an existing profile) with: name, URL, tier (see `policies/tiers.md`), owner contact, protected plugins, DB-migrating plugins, money paths (donate URL, checkout, register), forms and their expected recipient, mail provider, host, registrar.
2. **Transport choice.**
   - **ssh** (preferred): wp-cli over SSH with a key from the client's vault. Full checks. Check the key is `id_rsa`-style accepted by the host and the 1Password agent is unlocked for unattended runs.
   - **local**: you run on the host itself. A site reachable only by REST (no SSH) gets the unauthenticated checks (uptime, pages, mail) and the rest stay unmeasured.
3. **Capabilities.** Run the checks you can and record what stays unmeasured; note by hand: wp-cli version, PHP version, HPOS status, Action Scheduler, backup plugin and location, object cache, staging availability.
4. **Baselines**: record the first full check's findings as the baseline report; screenshot per viewport (mask dynamic regions); snapshot DNS records; record plugin and version inventory; record roster of users.
5. **Backups**: verify the 3-2-1 state and run a first restore drill before taking on changes.
6. **Ownership**: fill the handoff pack tables (`handoff-pack.md`). The client owns every account.
7. **Scope and SLA**: one page signed. Schedule: weekly light check, monthly session, quarterly board report.
8. **Tickets**: create the Linear project and labels if client tier.
9. **First cycle**: run the monthly cycle read-only and present the baseline digest.
