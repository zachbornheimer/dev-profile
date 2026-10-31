---
name: dependency-upgrade
description: Use when upgrading a dependency — changelog review, call-site grep, baseline tests on old version, upgrade, re-run tests (never weaken them), mise run ci, document old→new in the PR.
---

# Dependency Upgrade

A dependency upgrade is a code change. Treat it like one: prove behavior correct before and
after, never weaken a test to go green, document what changed for the reviewer.

## Gotchas (the defaults you break)

- **Never weaken a test to make the upgrade pass.** If a test now fails, the API or behavior
  changed — fix the _call site_ to match the new contract. A test that passes by accepting a
  weaker assertion is a latent bug, not a successful upgrade.
- **A patch or minor bump is not automatically safe.** Library authors make semver mistakes.
  One paragraph of changelog reading saves hours of debugging.
- **Grepping call sites is not optional.** Surprise breakage comes from the call sites you
  didn't check. Grep _every_ usage of the package's public API before touching the manifest.
- **Lockfiles are always committed.** `go.sum`, `package-lock.json`, `composer.lock` — all
  of them, every time. A lockfile-free upgrade is an untestable upgrade.
- **`mise run ci` is the gate, not `mise run test`.** Lint and build must also pass — the
  linter often catches deprecated API usage that the tests didn't exercise.
- **One atomic upgrade, not one package name.** A second package belongs in the same upgrade only when it is the caller the first package breaks (the CI log names it, or the lockfile shows it calling the removed API). Unrelated transitive bumps stay out. The diff is still one upgrade.

## Two passes

Pass 1 is this upgrade. A red check whose log names the package, or a caller of it, is the canary that the bump is not isolated. That caller joins this upgrade. Stay here until a fresh run of that check no longer names it.

Pass 2 starts only then. Red that does not name this upgrade is not this pull request. Arm automerge. `fix_red_ci` is the exception: one loop, only when the remaining red is still this repo and not this upgrade. It reports what it changed and whether the check went green.

## What runs together

The pull view and the file list start together. The tree search and the red-log fetch start together. The changelog waits until the diff has named the range. Usage waits until the changelog, the tree, and the red log are all in. The pull-request body and the edit start together after the facade decision. The re-check waits on the edit.

## Protocol

### 1. Review the changelog

Find the version range (old → new). Read every entry that could affect behavior: breaking
changes, deprecations, security advisories, behavior changes. If the project has GitHub
Security Advisories, check those too.

### 2. Baseline the old version

Run the full test suite before touching anything:

```bash
mise run test
```

Capture the output. If tests are already failing, stop — fix pre-existing failures in a
separate commit first. Otherwise your red/green story is meaningless.

### 3. Grep affected call sites

```bash
# Go
grep -rn '"<module-path>"' --include="*.go" .

# TypeScript / JavaScript
grep -rn "from '<package>'\|require('<package>')" --include="*.ts" --include="*.tsx" --include="*.js" .

# Python
grep -rn "import <package>\|from <package>" --include="*.py" .

# PHP
grep -rn "use <Vendor>\\\\<Package>" --include="*.php" .
```

List every call site. For each, check whether the new version changed the API at that point.

### 4. Upgrade the manifest and lockfile

```bash
# Go
go get <module>@<new-version> && go mod tidy

# Node
npm install <package>@<new-version>

# Python
uv add '<package>==<new-version>'

# PHP
composer require <vendor>/<package>:<new-version>
```

### 5. Fix call sites — never tests

Run `mise run test`. For each failure: read the error, update the call site to use the new
API. If a test itself tested a removed behavior that has a documented replacement, update
the test to test the equivalent new behavior at the same strictness level.

### Facade check

If fixing call sites in step 5 touched more than two files, the dependency has no
facade. That is the signal, not an accident. Per the Facade Rule: every system
boundary goes through an injectable facade whose name describes WHAT it does, not
HOW — `Cache` not `RedisCache`, `Store` not `SQLiteStore`. As part of this upgrade
(not a deferred follow-up), create that facade now and route all existing call sites
through it, so the dependency's API churn is absorbed in one file going forward.

Proportionality: 1–2 call sites or a dev-only tool → facade is optional. Widespread
use or any system boundary (HTTP client, storage, time, external SDK) → facade is
required. The next upgrade then becomes: update the facade, run the suite.

How to write facades the correct way is defined in the skill /agnostic-facades/SKILL.md

### 6. Full gate

```bash
mise run ci
```

Must be green. Lint and build too — not just the test suite.

### 7. Document in the PR description

- Old version → new version (exact, e.g. `v1.4.2 → v1.5.0`)
- Relevant changelog entries (paste the meaningful ones)
- Behavior changes that affect this codebase specifically
- Call sites updated and why

## Adding a net-new dependency (approval checklist)

Before adding a dependency that does not yet exist in the manifest:

- [ ] Is it necessary? (Can this be done in <50 stdlib lines?)
- [ ] Last commit within 6 months, multiple contributors (bus factor > 1)?
- [ ] License is MIT, Apache 2.0, BSD, or ISC?
- [ ] Minimal transitive dependency tree (not 200 transitive packages)?
- [ ] No org-standard alternative already in the manifest for this job?
- [ ] Answers to the above written in the PR description?

CODEOWNERS requires platform team approval for changes to `go.mod`, `package.json`,
`composer.json`, and equivalent lockfiles.
