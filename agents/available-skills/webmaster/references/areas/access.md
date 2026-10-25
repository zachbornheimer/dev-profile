# Access

**Check:** users and roles against the approved roster, Application Passwords, 2FA state, stale accounts, SSH keys — via wp-cli over the profile's transport (`wp user list`, `wp user application-passwords list`) and the hosting panel (finding IDs are `site:access:kind:subject`).

## Thresholds
- Any administrator not on the approved roster: finding (Sev2 if unknown).
- Quarterly audit of all roles against the roster; roster held in the site bible.
- Application Passwords bypass 2FA: list every one, owner and last used; any unused for 90 days or owned by a departed user is a finding.
- Shared logins: finding.
- Vault: one 1Password vault per client; membership matches the roster.

## Triage
- Unknown admin: treat as compromise until explained (`runbooks/incident-sev1.md`).
- Departed person still present: `runbooks/admin-offboarding.md` the same day.
- Member login issues: `runbooks/member-account-change.md`.

**Offboarding means:** remove the user, revoke Application Passwords, rotate SSH, DB and Stripe keys, remove third-party access.

**Backup rule applies to:** all removals and rotations; role changes above editor.

**Common misses:** Application Passwords left behind; hosting panel and registrar users forgotten; a "temporary" admin never removed.

**Cadence:** roster check monthly; full audit quarterly; offboarding on the day.
