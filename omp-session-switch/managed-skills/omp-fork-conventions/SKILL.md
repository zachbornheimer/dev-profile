---
name: omp-fork-conventions
description: "Branch, remote, CI assembly, and ephemeral-clone conventions for Zach's oh-my-pi fork (zachbornheimer/oh-my-pi). Use whenever committing, pushing, rebasing, auditing, or opening PRs in oh-my-pi."
---

# oh-my-pi Fork Conventions

Use whenever committing, pushing, rebasing, auditing, or opening PRs in `zachbornheimer/oh-my-pi`.

## Zero Load-Bearing Local Checkout
- `~/Developer/Personal/oh-my-pi` is intentionally NOT kept permanently on disk; pull/clone on demand into a worktree when editing, and never rely on `~/Developer/Personal/oh-my-pi` existing for routine checks or tool tests.
- `~/.omp/packages/omptype` holds the vendored `omptype` sources so `~/.omp/agent/tools/*/zod_for_tests.ts` works without a local `oh-my-pi` clone.
- `.github/workflows/protect-main.yml` runs the `verify-assembly` job in GitHub Actions on every PR to `main`, verifying `bun .omp-build/resolve-branches.ts` and dry-run merging all `.omp-build/branches/**/*.toml` branches in CI.
- Both `bash ~/.agents/available-skills/updating-oh-my-pi/scripts/probe-build.sh` and `audit_repo_branches` (`{ repo: "zachbornheimer/oh-my-pi", include_remote: true, base_ref: "origin/assembled" }`) work without a local checkout by initializing an ephemeral `--no-checkout --filter=blob:none` repository in `$TMPDIR`.

## Remotes
- `origin` -> `https://github.com/zachbornheimer/oh-my-pi.git` (the fork)
- `upstream` -> `https://github.com/can1357/oh-my-pi.git` (upstream)

## Branch Roles
1. **`feat/<slug>` or `fix/<slug>` (Topic branches)**
   - **MUST branch off pure `upstream/main` (`can1357/oh-my-pi:main`, e.g. `git merge-base upstream/main origin/main`)**, NEVER off fork `origin/main` or `origin/assembled`.
   - Why: fork `origin/main` carries fork-only commits (`.omp-build/*`, `.github/workflows/{omp-build,protect-main}.yml`, `omp-remote-target.ts`). Branching off fork `origin/main` pollutes any upstream PR against `can1357/oh-my-pi:main` with those fork-only files.
   - Verify before opening an upstream PR: `mb=$(git merge-base upstream/main feat/<slug>) && git diff --name-only "$mb"..feat/<slug> | grep -E '^\.omp-build/|omp-build\.yml|omp-remote-target'` must return empty.

2. **`main` (Fork main: `origin/main`)**
   - Holds `upstream/main` plus fork-only `.omp-build/` manifests (`.omp-build/branches/**/*.toml`, `.omp-build/resolve-branches.ts`, `.omp-build/rr-cache`, `.omp-build/merge-fix/`) and `.github/workflows/{omp-build,protect-main}.yml`.
   - Protected by `main-branch-guard.py` and `.github/workflows/protect-main.yml`: never push directly to `main`; land `.omp-build/branches/**/*.toml` updates via a small PR to `zachbornheimer/oh-my-pi:main`.

3. **`assembled` (`origin/assembled`, layer 10 in `.omp-build`)**
   - Integration branch merging `origin/main` and all active topic branches.
   - **Merge-only**: `omp-build.yml`, `protect-main.yml`, and `main-branch-guard.py` reject non-merge (`--first-parent --no-merges`) commits on `assembled`. Always integrate changes into `assembled` via `git merge --no-ff` (or multi-parent `git -c commit.gpgsign=false commit-tree`) from a topic branch.

4. **`omp-build` (`origin/omp-build`)**
   - Ephemeral CI release branch assembled automatically from `origin/main` + `.omp-build/branches/**/*.toml` on every `.github/workflows/omp-build.yml` run using `git merge --no-ff --no-edit --rerere-autoupdate` and `.omp-build/merge-fix/<branch>.patch`.
   - Never push to `omp-build` manually; trigger `gh workflow run omp-build.yml --repo zachbornheimer/oh-my-pi --ref main` (or merge a PR to `main`).

## Upstream PR Mergeability Gotcha (`CHANGELOG.md`)
- `.gitattributes` sets `packages/*/CHANGELOG.md merge=union`, so local `git merge` and `git merge-tree --write-tree` auto-resolve `CHANGELOG.md` conflicts that GitHub's `libgit2` mergeability checker still marks `CONFLICTING` (`DIRTY`).
- To test whether GitHub will report a conflict on a file touched by both `upstream/main` and your PR branch, run plain 3-way `git merge-file` on the blobs without `.gitattributes`.
