---
name: oh-my-pi-fork
description: Use whenever modifying oh-my-pi (~/Developer/Personal/oh-my-pi), releasing the custom omp build from the fork zachbornheimer/oh-my-pi, installing/updating omp via mise across macOS (MBP) and Linux (agent-fleet-backend / VPS), or preparing upstream PRs to can1357/oh-my-pi.
---

# oh-my-pi Fork: CI Build, mise Install, Upstream PRs

`~/Developer/Personal/oh-my-pi` is a local fork of `can1357/oh-my-pi` with two remotes:

- **`origin`** (`https://github.com/can1357/oh-my-pi.git`): upstream.
- **`fork`** (`https://github.com/zachbornheimer/oh-my-pi.git`): our fork. Its `main` is a **sacred upstream mirror** (`main == origin/main`, 0 custom commits); pushes to it are blocked by a GitHub ruleset, local commits by the reference-transaction hook (`bin/dev-profile-omp-machine-setup`, run by `mise run setup`) and `pretooluse-omp-main-branch-guard` (even with `DEV_PROFILE_ALLOW_DEFAULT_BRANCH_COMMIT=1`).

Design, release contract, and what the 2026-11-02 cutover removed: [references/build-distribution.md](references/build-distribution.md).

## 1. Adding or Updating a Custom Feature / Fix in `omp`

1. Branch a clean worktree off `origin/main` (never `main` directly, never commit on `main`):

   ```bash
   git -C ~/Developer/Personal/oh-my-pi fetch origin main
   wt -C ~/Developer/Personal/oh-my-pi switch --create feat/<slug> --base origin/main
   ```

2. Edit, format with `npx oxfmt` (`useTabs: true` per `.oxfmtrc.json` — never `dprint` on `oh-my-pi` `.ts` files), and run targeted `bun test` checks.
3. Commit on `feat/<slug>` and push the topic branch to `fork`:

   ```bash
   wt step commit
   git push -u fork feat/<slug>
   ```

4. List `feat/<slug>` in the fork's `.github/omp-rebuild.toml` on the fork's `ci` branch (the default branch; scheduled workflows run only from the default branch), then push.
5. CI (`.github/workflows/omp-build.yml`, daily 04:00 UTC + `workflow_dispatch`) assembles `omp-build` from upstream `main` + the listed branches in order. On conflict it fails, publishes nothing, and opens/updates one GitHub issue naming the branch and files; the previous release stays `latest`.
6. Install the new release everywhere: `mise up github:zachbornheimer/oh-my-pi` (the daily launchd/systemd jobs run exactly this).

## 2. Removing a Branch From Our Custom `omp` Build

Delete `feat/<slug>` from the fork's `.github/omp-rebuild.toml` on `ci`, push, and let CI build the next release (or trigger it with `gh workflow run omp-build.yml --repo zachbornheimer/oh-my-pi`).

## 3. Installing and Updating `omp`

- **mise tool** (global `~/.config/mise/config.toml`, seeded from dev-profile `config/mise.toml`):
  `"github:zachbornheimer/oh-my-pi" = { version = "latest", matching = "omp-", minimum_release_age = "0" }`.
  `minimum_release_age = "0"`: the fork's own CI builds these releases, so the 24h supply-chain holdback default would hide each day's build until the next.
- **Verify**: `mise which omp && omp --version` (plus `env -i HOME="$HOME" PATH="$HOME/.local/bin:/usr/bin:/bin" ~/.local/bin/omp --version` for the entrypoint below).
- **Daily update**: runs at `05:00` — macOS: the mise launchd agent `dev.mise.omp-daily-sync` from `~/.config/mise/config.toml` (`mise bootstrap macos launchd-agents apply --yes`); Linux: the systemd user timer `omp-daily-sync.timer` (`apps/omp/omp-daily-sync.service` in dev-profile). Both run `mise up github:zachbornheimer/oh-my-pi`.
- **Release tags**: `build-<YYYYMMDD>-<upstream-short-sha>-<build-short-sha>`, marked latest, never prerelease. Assets: `omp-darwin-arm64.tar.gz`, `omp-linux-x64.tar.gz` (one top-level `omp` executable), plus `SHA256SUMS`.
- **Stable entrypoint**: `~/.local/bin/omp` — a symlink to the mise shim (`../share/mise/shims/omp`), created idempotently by `bin/dev-profile-omp-machine-setup` (`mise run setup`) on every machine. Consumers whose PATH has `~/.local/bin` without the shims dir (the capability gateway shells out to plain `omp`) depend on it: never delete it. `mise which omp` resolves the real install; both run the same release binary.
