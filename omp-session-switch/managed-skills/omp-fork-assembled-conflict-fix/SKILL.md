---
name: omp-fork-assembled-conflict-fix
description: "Resolve origin/assembled merge conflicts, omp-build.yml CI failures, and upstream PR compliance in zachbornheimer/oh-my-pi. Use when updating assembled, .omp-build/branches/*.toml, or upstream PRs to can1357/oh-my-pi."
---

# Fixing `origin/assembled` Merge Conflicts & `omp-build.yml` Failures in `oh-my-pi`

When `can1357/oh-my-pi:main` advances and `zachbornheimer/oh-my-pi`'s `omp-build.yml` workflow fails in `Assemble omp-build` or `Build omp`, use these verified invariants:

## 1. Branch Manifest Schema (`.omp-build/branches/**/*.toml`)
- `.omp-build/resolve-branches.ts` strictly validates keys and ONLY allows: `reason`, `upstream` (`"no" | "candidate" | "submitted"`), `pr` (required when `upstream = "submitted"`), and `layer` (integer, default `50`).
- Never add `requires` or `summary` keys to `.omp-build/branches/**/*.toml` — `resolve-branches.ts` will fail the build with `unknown key`.
- Changes to `.omp-build/**` and `.github/workflows/{omp-build,protect-main}.yml` on `main` must be opened as single-parent commits off `origin/main` so the `protect-main / Protect main carry paths` check passes.

## 2. `assembled` Integration Branch Invariants
- Both local `.git/hooks/reference-transaction` and CI (`omp-build.yml`) reject direct single-parent commits on `assembled`. Every update to `assembled` must be a merge commit (`git commit-tree <tree> -p <assembled> -p <topic_or_main>`).
- **`packages/coding-agent/src/modes/controllers/event-controller.ts`**: `omp-build.yml` unconditionally runs `git apply --index .omp-build/merge-fix/assembled.patch` after merging `assembled`. Keep `event-controller.ts` on `assembled` at its pre-patch state (with the 5 `#blockingPrompt` lines intact) so `git apply --index` succeeds during `Assemble omp-build` and removes them for the build.
- **`crates/pi-builtins/Cargo.toml`**: Must contain BOTH `stacker = "0.1.25"` (used by `jq`) AND `tempfile = "3.15.0"` (used by `crates/pi-builtins/src/awk/interp.rs`).
- **`packages/coding-agent/src/session/session-listing.ts`**: When resolving conflicts between `assembled` and `upstream/main`, preserve `clearSessionListingCache` from `assembled` (`resolve_hunks(..., "ours")`), or `Bun.build` in `compile-binary.ts` will fail with `No matching export in "src/session/session-listing.ts" for import "clearSessionListingCache"`.
- **Changelogs (`packages/*/CHANGELOG.md`)**: `.gitattributes` sets `CHANGELOG.md merge=union`, which duplicates headings across merges. Always run `bun scripts/fix-changelogs.ts` and verify `bun scripts/fix-changelogs.ts --check` reports `Changelogs already clean` before committing the `assembled` tree.

## 3. Upstream PR Branches (`can1357/oh-my-pi`)
- Keep each upstream PR branch as a **single linear commit** directly on top of `can1357/oh-my-pi:main` (`upstream/main`). Avoid `git merge upstream/main` on upstream PR branches: GitHub does not honor `.gitattributes` `merge=union` when computing PR mergeability across multi-ancestor histories and will mark `CHANGELOG.md` as `CONFLICTING` (`DIRTY`).
- Place all `CHANGELOG.md` entries under `## [Unreleased]` (`### Added` / `### Fixed` / `### Changed`), preserve the trailing `\n` at EOF, and verify with `bun scripts/fix-changelogs.ts --check`.
- Scrub fork-private or personal strings (`zbornheimer`, `worktrunk`, `wt switch`, `wt remove`, `"build-latest"`) from upstream PR branches.
- Match `.github/PULL_REQUEST_TEMPLATE.md` and `CONTRIBUTING.md`: title ≤72 chars matching the commit subject, `## What` opening with a first-person explanation of what changed and why, `## Why`, and `## Testing` with a live session exercise scenario plus `bun test` / `bunx oxlint` / `bun scripts/fix-changelogs.ts --check`.
