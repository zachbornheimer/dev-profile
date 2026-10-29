# Updates

**Check:** core, plugins, themes, PHP, plugin abandonment, changelog risk — wp-cli inventory over the profile's transport plus the wp.org API (finding IDs are `site:updates:kind:subject`).

**Order:** backup, core, plugins one at a time (WooCommerce first, then its extensions), then themes. See `runbooks/plugin-update.md`.

## Key facts

- WooCommerce and its extensions migrate the database. A file rollback does not undo that; restore DB and files from the same moment.
- Closed or abandoned plugins appear via the wp.org API (closed, not updated in 2+ years, tested-up-to far behind).
- `wp plugin verify-checksums` does not cover premium plugins; use vendor version data.
- PHP 8.1 reached end of life on 2025-12-31. PHP 8.2 and earlier are findings on a timeline; plan the upgrade.

## Triage

- Security update for an installed plugin: raise urgency (see `policies/severity-sla.md`, 24-72h).
- Minor/patch, low risk: auto after backup, every tier.
- Major version, DB migration, or protected: back up files and DB first, then update.
- Low-confidence changelog judgment: ask.
- Plugin closed on wp.org or abandoned: ticket to replace.

**Backup rule applies to:** protected and DB-migrating plugins; core majors; PHP changes; plugin replacements.

**Common misses:** running `update --all`; updating WooCommerce extensions before WooCommerce; ignoring themes and mu-plugins; not re-probing checkout after an update.

**Cadence:** check weekly; apply in the monthly session; security patches out of cycle.
