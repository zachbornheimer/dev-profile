---
name: updating-oh-my-pi
description: Use when landing a new branch into the custom omp build (fork zachbornheimer/oh-my-pi), adding or removing a branch from that build, fixing a failed omp-build run or conflict issue, or installing, updating, verifying or rolling back omp via mise on the Mac and the fleet.
---

# Updating oh-my-pi: landing a branch in the custom omp

The `omp` you run is **upstream `can1357/oh-my-pi` main + an ordered list of topic branches**, assembled and built once in GitHub Actions on the fork `zachbornheimer/oh-my-pi`, published as a release, and installed everywhere by mise.

- Checkout: `~/Developer/Personal/oh-my-pi`. Remotes: **`origin`** = upstream `can1357/oh-my-pi`, **`fork`** = `zachbornheimer/oh-my-pi`.
- **`main` is a read-only upstream mirror.** Never commit, merge or push to it. A GitHub ruleset, the local reference-transaction hook (installed by `bin/dev-profile-omp-machine-setup`) and `pretooluse-omp-main-branch-guard` all refuse it. Do not bypass them.
- **The branch list** is `.github/omp-rebuild.toml` (`branches = [ ... ]`, merged in order) on the fork's default branch **`ci`**. `ci` holds only that file, `.github/workflows/omp-build.yml` and `scripts/omp-build/resolve-branches.ts`.
- **CI** (`omp-build`, daily 04:00 UTC + manual dispatch) merges each listed branch with `git merge --no-ff` onto upstream main, builds darwin-arm64 + linux-x64, and publishes release `build-<YYYYMMDD>-<upstream7>-<build7>` as Latest.

Design and history: [references/build-distribution.md](references/build-distribution.md).

## Land a new branch (in order)

1. **Branch off upstream in a worktree**, never off `main`:

   ```bash
   git -C ~/Developer/Personal/oh-my-pi fetch origin main
   wt -C ~/Developer/Personal/oh-my-pi switch --create feat/<slug> --base origin/main
   ```

2. **Build the change.** Format with `npx oxfmt` (`useTabs: true` per `.oxfmtrc.json`; never `dprint` on oh-my-pi `.ts`). Run `bun check` and the targeted `bun test` files. Commit with `wt step commit`.
3. **Push the branch to the fork:** `git push -u fork feat/<slug>`.
4. **Probe the assembly exactly as CI will** (must exit 0):

   ```bash
   ~/.agents/skills/updating-oh-my-pi/scripts/probe-build.sh --add feat/<slug>
   ```

   It fetches `origin/main`, `fork/ci` and every listed branch, then merges them in order with `git merge-tree` (no branch is changed). `CONFLICT ... with upstream main`: merge `origin/main` into your branch, resolve, push. `CONFLICT ... with an earlier branch in the list`: merge that branch into yours (or yours into it) and resolve once, so the later branch in the list already contains the resolution. **Merge, never rebase or force-push** a branch that is pushed or listed.
5. **Add the branch to the list on `ci`:**

   ```bash
   git -C ~/Developer/Personal/oh-my-pi fetch fork ci
   wt -C ~/Developer/Personal/oh-my-pi switch ci   # first time: switch --create ci --base fork/ci
   git pull --ff-only fork ci
   # edit .github/omp-rebuild.toml: append "feat/<slug>" to branches (after any branch it depends on)
   wt step commit && git push fork ci
   ```

   If the branch makes another listed branch redundant (it contains it: `git merge-base --is-ancestor fork/<old> fork/feat/<slug>`), replace that entry instead of appending. Re-run the probe with no flags: it reads the pushed list.
6. **Build now** instead of waiting for 04:00 UTC, and watch the exact run id:

   ```bash
   gh workflow run omp-build.yml --repo zachbornheimer/oh-my-pi --ref ci
   gh run list --repo zachbornheimer/oh-my-pi --workflow omp-build.yml --limit 1 --json databaseId --jq '.[0].databaseId'
   gh run watch <that-id> --repo zachbornheimer/oh-my-pi --exit-status
   ```

   Copy the id; a mistyped id makes `gh run watch` return at once and look like success. A cold build (upstream touched Rust) takes about 23 min; warm about 4 min; no change since the latest release skips the build after about 1 min.
7. **Install and prove the branch is in the binary** on each machine (the daily jobs do the install at 05:00 local, but do not wait):

   ```bash
   mise up github:zachbornheimer/oh-my-pi
   mise latest github:zachbornheimer/oh-my-pi        # the new tag
   rg -a -c -F '<string only your branch adds>' "$(mise which omp)"   # > 0
   ```

   `omp --version` is NOT proof: an upstream-only build prints the same version. Fleet: run the same three lines over `ssh backend.ai`.

Do not use `branches_override` to land anything. A dispatch with a non-empty override publishes a **prerelease**, which mise never installs; it is for experiments only.

## When a run fails

| Run error                                                                                                 | Cause                                                                      | Fix                                                                                                                          |
| --------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| `Conflict: omp-build: <branch> conflicts with upstream` (one GitHub issue per branch, updated on repeats) | That branch conflicts with upstream main or with a branch merged before it | Run the probe to see which; fix as in step 4; push; re-dispatch; close the issue                                             |
| `Missing branch`                                                                                          | A listed branch is not on the fork                                         | Push it, or remove it from the list                                                                                          |
| `Branchless assembly`                                                                                     | The assembled SHA equals upstream (empty list)                             | Restore the list; CI refuses to publish plain upstream                                                                       |
| Build or publish job failed                                                                               | Compile or test error on the assembled tree                                | Reproduce on the probe's result: `git merge` the listed branches into a scratch worktree off `origin/main`, then `bun check` |

A failed run publishes nothing; the previous release stays Latest, so every machine keeps working.

## Remove a branch

When upstream has merged a branch, `git cherry origin/main fork/feat/<slug>` prints only `-` lines. Delete it from `.github/omp-rebuild.toml` on `ci` (step 5), run the probe, push, dispatch (step 6).

## Install facts

- mise tool (global `~/.config/mise/config.toml`, seeded from dev-profile `config/mise.toml`): `"github:zachbornheimer/oh-my-pi" = { version = "latest", matching = "omp-", minimum_release_age = "0" }`. `minimum_release_age = "0"` because the fork's own CI builds each release; the 24h default would hide every daily build.
- Stable entrypoint `~/.local/bin/omp` is a symlink to the mise shim, created by `bin/dev-profile-omp-machine-setup` (`mise run setup`). The capability gateway runs plain `omp` with only `~/.local/bin` on PATH: never delete it. Check: `env -i HOME="$HOME" PATH="$HOME/.local/bin:/usr/bin:/bin" ~/.local/bin/omp --version`.
- Daily update: macOS launchd agent `dev.mise.omp-daily-sync`, Linux systemd user timer `omp-daily-sync.timer`; both run `mise up github:zachbornheimer/oh-my-pi`.

## Roll back one machine

Pin a known-good tag in the machine-local `~/.config/mise/config.local.toml` (not synced), then `mise install`:

```toml
# ROLLBACK <date>: <why>. Remove once a fixed release is Latest.
[tools]
"github:zachbornheimer/oh-my-pi" = "build-<YYYYMMDD>-<upstream7>-<build7>"
```

Delete the block and run `mise up github:zachbornheimer/oh-my-pi` to return to Latest. Check `gh release list --repo zachbornheimer/oh-my-pi` for tags; never pin a prerelease.
