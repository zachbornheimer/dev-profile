---
name: migrations
description: Use when creating, applying, or reviewing a database migration (Atlas, versioned *.sql migrations, schema changes). Idempotent + safety-linted. For column types/conventions, pairs with the `sql` skill.
---

# Database Migrations (Atlas, idempotent, safety-linted)

The migration directory is the **source of truth**; the live DB must never drift
from it (`atlas migrate status`). Migrations are **idempotent** — applying twice is
a safe no-op — and every migration is **linted before it ships**, the same way the
`api` skill treats Spectral. A migration that locks a production table or breaks an
in-flight client is the failure mode to design against.

## Workflow (Atlas, contract-first)

1. Change the desired schema (declarative HCL/SQL) — don't hand-write the migration.
2. `atlas migrate diff <name>` — Atlas computes the migration from the schema change.
3. **`atlas migrate lint`** — THE GATE. It catches destructive ops, backward-
   incompatible changes, and non-idempotent/data-dependent statements. A red lint
   doesn't ship; wire it into `mise run lint` / CI.
4. Review the generated SQL against the safety rules below.
5. `atlas migrate apply` — applies only _pending_ revisions (tracked in
   `atlas_schema_revisions`), so re-running is a no-op. Provide a down migration.

## Idempotency

- Atlas apply is idempotent by revision tracking — never re-run a completed
  migration by hand; let Atlas decide what's pending.
- When you must hand-write DDL, guard it: `CREATE TABLE IF NOT EXISTS`,
  `DROP ... IF EXISTS`, `ADD COLUMN IF NOT EXISTS`. The statement must survive a
  re-run.

## Safety rules (from `sql`)

- **Additive-only in production.** Add, don't remove/rename/retype in the same deploy.
- **Nullable-first.** Add a column nullable → backfill in a separate step → set
  `NOT NULL` in a later migration. Never `NOT NULL` without a default on a large table.
- **`CREATE INDEX CONCURRENTLY`** on live tables — a plain `CREATE INDEX` takes an
  `ACCESS EXCLUSIVE` lock and blocks writes.
- **Expand-contract for renames:** add the new column → dual-write → migrate reads →
  drop the old one in a later release. A rename in one migration breaks clients
  mid-flight.
- **Reversible:** every migration has a tested down. Types: `TIMESTAMPTZ`,
  `NUMERIC` for money, `created_at`/`updated_at` on every table.

## Gotchas

- The dangerous locks are silent: adding a `NOT NULL` column with a volatile
  default, changing a column type, or a non-concurrent index build — each can hold
  an `ACCESS EXCLUSIVE` lock and stall prod. `atlas migrate lint` flags most; respect it.
- Don't "fix" a drift by editing an already-applied migration — write a new one.
  Editing applied history corrupts the revision ledger.
- Data backfills belong in their own migration/step, not bundled with the DDL that
  adds the column — keep schema and data changes separately revertible.
