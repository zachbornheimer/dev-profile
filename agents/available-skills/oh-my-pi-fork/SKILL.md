---
name: oh-my-pi-fork
description: Use whenever modifying oh-my-pi (~/Developer/Personal/oh-my-pi), building or syncing the custom omp binary across macOS (MBP) and Linux (agent-fleet-backend / VPS), or preparing upstream PRs to can1357/oh-my-pi.
---

# oh-my-pi Fork, Build, and Upstream PR Workflow

`~/Developer/Personal/oh-my-pi` is maintained as a two-remote fork across macOS (`darwin-arm64`) and the Linux compute arm (`agent-fleet-backend`, `linux-x64`) with **strict branch isolation** enforced by `dev-profile/config/omp-rebuild.toml`:

- **`origin`** (`https://github.com/can1357/oh-my-pi.git`): Upstream repository.
- **`main` (`local` and `fork/main`):** **Sacred upstream mirror (`main == origin/main`, 0 custom commits).** Direct commits or merges onto `main` in `oh-my-pi` are **forbidden and mechanically blocked** by `dev-profile-no-commit-to-default-branch` and `pretooluse-omp-main-branch-guard` (even if `DEV_PROFILE_ALLOW_DEFAULT_BRANCH_COMMIT=1` is set).
- **Topic Branches (`fork/<branch>` on `zachbornheimer/oh-my-pi`):** Every custom feature or fix lives on its own named topic branch branched off `origin/main` and pushed to `fork/<branch>`.
- **`dev-profile/config/omp-rebuild.toml` (`branches = [...]`):** The single declarative source of truth listing which topic branches are included in our custom `omp` build.
- **`omp-build` (`fork/omp-build`):** The integration branch built by `dev-profile-omp-sync` from `origin/main` + the branches listed in `dev-profile/config/omp-rebuild.toml`.
- **`~/.local/bin/omp`:** The active binary on `$PATH`, compiled from `omp-build`.

## 1. Adding or Updating a Custom Feature / Fix in `omp`

1. Always branch a clean worktree off `origin/main` (never `main` directly, and never commit on `main`):

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

4. Register `feat/<slug>` in `dev-profile/config/omp-rebuild.toml`, rebuild `omp-build`, install `~/.local/bin/omp`, and push `fork/omp-build` in one command:

   ```bash
   dev-profile-omp-sync --include feat/<slug> --push
   ```

Every run rebuilds `omp-build` from scratch: `origin/main`, then each configured branch merged in order, in the build worktree `~/Developer/Personal/.worktrees/oh-my-pi-omp-build`. Never check out `omp-build` or commit to it; the sync refuses to run while it is checked out. A branch that conflicts exits non-zero and installs nothing. Fix it once, either way:

- rebase the branch onto `origin/main` and push it, or
- in the build worktree, `git merge <branch>`, resolve, `git commit`; `git rerere` replays that resolution on every later run.

## 2. Removing a Branch From Our Custom `omp` Build

When upstream merges one of our PRs or we no longer want a branch in our build:

```bash
dev-profile-omp-sync --exclude feat/<slug> --push
```

That removes `feat/<slug>` from `dev-profile/config/omp-rebuild.toml`, rebuilds `omp-build` cleanly from `origin/main` + the remaining configured branches, and updates `~/.local/bin/omp`.

## 3. Syncing & Verifying Across MBP and VPS (`agent-fleet-backend`)

- **Check status, `main == origin/main` invariant, and configured branches:**

  ```bash
  dev-profile-omp-sync --status
  ```

- **Manual rebuild on either machine (MBP or VPS):** `omp-rebuild` (the zsh shorthand) or

  ```bash
  dev-profile-omp-sync
  ```

- **Run log:** `~/.local/state/omp-sync.log`; a failed run starts its last line with `FAILED:`.
- **Automatic daily sync:** Runs daily at `05:00` via `omp-daily-sync.timer` (Linux systemd user timer) and `com.zbornheimer.omp-daily-sync.plist` (macOS LaunchAgent).
