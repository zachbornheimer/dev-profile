---
name: codebase-upgrade
description: Pre-production QUALITY upgrade — clean, modernize, and prepare for maintainability. Use when asked to upgrade or clean the codebase, distinct from dependency-upgrade (which bumps package versions) and audit (which targets one file).
---

# Codebase Upgrade

A whole-codebase quality pass. Pre-production freedom: delete aggressively,
rename freely, restructure without backward-compatibility worry. The goal is
code a FAANG L8 would approve, not code that merely compiles.

## Hard rules

- **Plan → approve → execute. Never skip the approval gate.** Present the full
  plan table and receive explicit "proceed" before touching a file.
- **Test + commit after every category.** Lint must be green; tests must be
  green; _then_ commit. Fix failures immediately — don't continue to the next
  category with a red suite.
- **One commit per category.** Seven categories → seven commits. One giant
  commit at the end is useless for bisect and review.

## Phase 1 — Inventory (analysis only, no edits)

Collect:

- All source files by language + rough line counts.
- Every direct system call (os, time, rand, http, env, exec) — per-language
  grep patterns are in `cursor/commands/codebase-upgrade.md`.
- Names that expose implementation (SQLite, Parallel, Async, Redis, Proto...).
- Leaky comments ("uses goroutines", "implemented with sqlite").
- Dead/deprecated code (`@deprecated`, `TODO: remove`, commented-out blocks,
  unused exports).
- Duplicate function definitions.
- Files over 500 lines.
- Tests without assertions or with implementation names.

## Phase 2 — Issues

Compile a findings table:

| # | File     | Line | Category  | Current       | Proposed     |
| - | -------- | ---- | --------- | ------------- | ------------ |
| 1 | store.go | 45   | Bad name  | `SQLiteStore` | `EventStore` |
| 2 | utils.go | all  | Dead code | entire file   | delete       |

Then a priority table by category and estimated change count.

## Phase 3 — Present plan and wait for approval

Show both tables. Ask:

> "I've analyzed the codebase. Ready to execute? I'll make changes by category,
> run tests after each, commit after each passing category, and stop to fix any
> failures before continuing. Proceed?"

Do not proceed to Phase 4 until the user says yes.

## Phase 4 — Execute by category (in this order)

### 1. Dead code

Delete unused functions, commented-out code, `TODO: remove` items, deprecated
alternatives, entire unused files. No deprecating what can be deleted.

### 2. Duplicates

Create a shared home (`internal/shared/`, `src/lib/`, `lib/`) for the
consolidated helper. Update every caller. Delete all duplicates.

### 3. Bad names (implementation-exposing)

`SQLiteStore → EventStore`, `ParallelWalk → Walk`, `RedisCache → Cache`,
`ProtoSerializer → Serializer`. Names describe WHAT, not HOW.

### 4. Leaky comments

`"uses goroutines for parallel processing"` → `"processes concurrently"`.
`"SQLite database for caching"` → `"local cache for fast lookups"`.
Comments explain WHY, not HOW.

### 5. Direct system calls → facades

Use the existing facade if one exists. If not, introduce it completely:
interface + real impl + fake/mock + lint rule + all call sites migrated. See
`audit` skill for the full facade-introduction checklist.

### 6. Oversized files

Files over 500 lines → split by responsibility (types, service, repository,
handler, helpers). Functions over 50 lines → extract named sub-functions.

### 7. Test quality

Rename `TestSQLiteStore` → `TestEventStore_SavesAndRetrieves`. Add missing
assertions. Replace direct system calls with fakes. Remove timing dependencies
(`time.Sleep` → channels/waitgroups).

## Phase 5 — Final verification

Re-run all linters + full test suite. Re-run the Phase 1 greps; the result
should be empty (or each hit justified). Push all commits.

## Gotchas

- **This is not `dependency-upgrade`.** Don't bump package versions here.
- **This is not `audit`.** Audit targets one file; this targets the codebase
  shape. Use audit for semantic depth on a single file after this pass.
- **Test failures in category N mean stop and fix, not skip to category N+1.**
  A red suite carried forward masks regressions from the next category.
- **Introducing a facade without migrating all callers or adding a lint rule**
  is leaving the hole open. See the facade checklist in `audit`.
