---
name: audit
description: Use when auditing a file for quality — beyond what the linter already catches. Zero-deferrals, pattern-inventory, and facade-checklist are the novel principles. Not for dependency upgrades (use dependency-upgrade) or whole-codebase cleanup (use codebase-upgrade).
---

# Audit

A code audit has one mission: leave the codebase **more resistant to future
mistakes**, not just fix the current instance. Fixing a bug without preventing
its class is maintenance, not improvement.

## The four novel principles

### 1. Zero-deferrals

Every finding is fixed in the same audit pass — no "track for later," no
"low priority backlog," no out-of-scope excuses. If you found it, fix it or
delete it. The only exception is a finding that requires a user-only decision
(product call, destructive action); those are escalated immediately, not noted
for someday.

### 2. Independent discovery

You must find issues _beyond_ what the linter already reported. Running the
linter and transcribing its output is not auditing — that is just CI locally.
The audit value lives in the things the linter cannot see: mismatched intent vs.
name, a magic value whose origin no one can explain, a test that passes for the
wrong reason, a system call that escaped facade coverage.

### 3. Pattern inventory before fixing

Before touching a single line, build a **Pattern Inventory table**: every
recurring code shape in the file (direct system calls, error patterns,
constants, concurrency shapes, etc.) with a count of instances. This prevents
whack-a-mole — you fix the pattern structurally, not each instance in turn.

| Pattern             | Instances | Current form | Correct form                   |
| ------------------- | --------- | ------------ | ------------------------------ |
| Direct `time.Now()` | 4         | inline       | `timeSource.Now()`             |
| Bare `return err`   | 7         | no context   | `fmt.Errorf("op %s: %w", ...)` |

Fix each pattern once (create the structure), then migrate all instances.

### 4. Facade-introduction checklist

When the audit reveals a missing facade (a system boundary hit directly),
introduce it completely — not a partial stub:

- [ ] Interface definition (the contract)
- [ ] Real implementation (`Real*`)
- [ ] In-memory / fake for tests (`Fake*` or `Mock*`)
- [ ] All existing call sites migrated
- [ ] Lint rule added to block future direct calls
- [ ] Tests updated to use the fake

Introducing the interface without migrating callers or adding a lint rule is
leaving a hole you'll audit again next quarter.

### 5. Touched-file audit

Any file you _create_ or _significantly modify_ during the audit gets a
mini-audit pass. Creating a non-compliant helper while fixing a compliance issue
in the target file is the canonical self-own.

## Order of work

1. Run the linter — document all output, fix nothing yet.
2. Read the file fully. Build the Pattern Inventory.
3. Independent discovery pass — find what the linter missed.
4. Compile findings (all categories, zero deferrals).
5. Introduce facades / lint rules before implementing fixes.
6. Implement all fixes, migrate all call sites.
7. Write or update tests — every new path has a test.
8. Re-run linter + tests; verify green.
9. Audit any new files created in steps 5–6.
10. Commit. One commit per audited file.

## Gotchas

- **"Looks reasonable" is not semantic analysis.** For every constant, threshold,
  or magic number, ask: where did this value come from, and would the runtime
  handle this without it? If no measured evidence exists for a runtime override,
  the override ships without it — remove it, don't document it. See
  `references/standards.md` §trust-the-runtime.
- **Creating non-compliant code during a compliance audit is the failure mode.**
  Run a mini-audit on every file you create, not just the target.
- **Pattern inventory prevents the linter-mode trap.** Without it you fix the
  instance under your cursor and leave seven others.
