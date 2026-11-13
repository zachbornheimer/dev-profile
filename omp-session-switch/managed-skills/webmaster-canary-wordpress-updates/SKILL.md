---
name: webmaster-canary-wordpress-updates
description: "Run read-only update plans and ticketed single-plugin updates across the webmaster sites (bpp, isjac, zbm, zysys) when the webmaster-agent route is unavailable, including money-path plugins."
---

# Canary WordPress updates (webmaster-site workflows, run directly)

Use when asked to "check what tools exist and update the plugins". Code lives in `capability-replicas/mastra/webmaster-site`. Run commands through `run_command`, tests with `bun test` (not vitest, not npx).

## 1. Plan (read-only)
Throwaway runner: build a `Mastra` with `LibSQLStore({url: ":memory:"})`, register `webmasterWorkflows.siteUpdatesPlan`, `createRun().start({inputData: {site, planPath: "/tmp/canary/<site>-plan.json"}})`. Read the JSON `steps`: kind, slug, from, to, level, disposition, `money`, `cautions`. Tiers are in `sites/<site>.yaml` (isjac client, zbm personal, zysys/bpp business). A site with no `host:` block (bpp) is unmeasured.

## 2. Update one plugin at a time
Register `webmasterWorkflows["webmaster.wordpress.updating"]`, input `{site, plugin, ticket, approvedBy?}`. Needs an OPEN atask ticket in project `webmaster:<site>` (`atask list open --project webmaster:<site>`). Client/business tier money-path plugins need `approvedBy`. Money-path plugins (profile `updates.money_paths`) get: backup before and after, store check, checkout page check, files-only rollback. Never restore the database over a live store.
Outcomes: `applied`, `restored` (verify failed, files put back), `backup_failed` (nothing changed). Result lines carry the backup dir and rollback command.

## 3. Hold, do not force
- Money plugins that migrate their database (Memberships, Name Your Price, Subscriptions) or are major releases: ask first, one at a time.
- Premium plugins that need a licence connection (AudioTheme Agent) fail the update command and restore; not fixable by retry.
- Before backing up a site, scan for foreign plugins. zbm had `commentcleaner` (obfuscated, hides itself from the plugin list). Back up after cleanup, not before.

## Known traps
- Plesk hosts (zbm): backup dir is owned by the site user; every read of it must go through `file_prefix` (fixed in 8a1b60d66a).
- `ask_mastra webmaster-agent` can fail with a host-tool name conflict on `webmaster_page_audit` (custom tool in `~/.omp/agent/tools`); run workflows directly instead.
- Edit tools race when two edits to one file are issued in parallel and can corrupt the file; issue edits sequentially.
- Verify live versions after: `ssh <host> 'cd <root> && wp plugin list --fields=name,version,update'` (isjac has no `rg`; use grep).
