---
name: oh-my-pi-fork
description: Use whenever modifying oh-my-pi (~/Developer/Personal/oh-my-pi), building or syncing the custom omp binary across macOS (MBP) and Linux (agent-fleet-backend / VPS), or preparing upstream PRs to can1357/oh-my-pi.
---

# oh-my-pi Fork, Build, and Upstream PR Workflow

`~/Developer/Personal/oh-my-pi` is maintained as a two-remote fork across macOS (`darwin-arm64`) and the Linux compute arm (`agent-fleet-backend`, `linux-x64`):

- **`origin`** (`https://github.com/can1357/oh-my-pi.git`): Upstream repository. **Never** commit personal patches onto `origin/main`, and **never** branch upstream PRs off local `main`.
- **`fork`** (`https://github.com/zachbornheimer/oh-my-pi.git`): Personal fork. `fork/main` holds the combined daily-driver stack (upstream PR branches + personal `capability` MCP / `xdev` / session patches).
- **`~/.local/bin/omp`**: The active binary on `$PATH` (precedes `/opt/homebrew/bin/omp`). Editing TypeScript in `packages/*` does **not** update a compiled `~/.local/bin/omp` binary until `dev-profile-omp-sync --compile` runs (which happens **automatically** on `wt merge` / `wt step commit` on `main` via `worktrunk.toml`).

## 1. Making a Personal / Fleet Change to `omp` (Automatic Build & Sync)

1. Create a worktree from `main`:
   ```bash
   wt -C ~/Developer/Personal/oh-my-pi switch --create feat/<slug>
   ```
2. Edit, format with `npx oxfmt` (`useTabs: true` per `.oxfmtrc.json` — never `dprint` on `oh-my-pi` `.ts` files), and run targeted `bun test` checks.
3. Commit and merge into `main`:
   ```bash
   wt step commit
   wt merge
   ```
   **What happens automatically (`~/.config/worktrunk/config.toml` `[post-merge]` & `[post-commit]`):**
   When a change lands on `main` in `oh-my-pi`, Worktrunk automatically invokes:
   ```bash
   ~/.local/share/dev-profile/bin/dev-profile-omp-sync --compile --push
   ```
   which runs `bun install`, ensures the platform native addon (`pi_natives.darwin-arm64.node` or `pi_natives.linux-x64-modern.node`), compiles `packages/coding-agent/dist/omp`, installs/signs `~/.local/bin/omp` (recording the SHA in `~/.local/bin/.omp-sha`), and pushes `fork/main` so both the MBP and `agent-fleet-backend` stay in lockstep.

## 2. Opening or Updating an Upstream PR to `can1357/oh-my-pi`

Upstream PRs **must** be branched directly from `origin/main` so personal `capability` / `wait` patches never leak into upstream PR diffs:

1. Create a clean worktree branched off `origin/main`:
   ```bash
   git -C ~/Developer/Personal/oh-my-pi fetch origin main
   wt -C ~/Developer/Personal/oh-my-pi switch --create feat/<upstream-pr-slug> --base origin/main
   ```
2. Implement **only** the upstream feature/fix in that worktree.
3. Format touched files with `npx oxfmt` and verify `npx oxfmt --check` passes (upstream uses tabs, `tabWidth: 3`, `printWidth: 120` in `.oxfmtrc.json`).
4. Commit and push the clean branch to `fork`:
   ```bash
   wt step commit
   git push -u fork feat/<upstream-pr-slug> --force-with-lease
   ```
5. Fold the upstream branch into your personal daily-driver `main`, compile `~/.local/bin/omp`, and push `fork/main` in one command:
   ```bash
   dev-profile-omp-sync --include feat/<upstream-pr-slug> --compile --push
   ```

## 3. Syncing & Verifying Across MBP and VPS (`agent-fleet-backend`)

- **Check status anytime:**
  ```bash
  dev-profile-omp-sync --status
  ```
- **Manual sync + compile on either machine (MBP or VPS):**
  ```bash
  dev-profile-omp-sync --compile
  ```
- **Automatic daily sync:** Runs daily at `05:00` via `omp-daily-sync.timer` (Linux systemd user timer) and `com.zbornheimer.omp-daily-sync.plist` (macOS LaunchAgent).
- **VPS spin-up (`dev-env` `mise run vps:up`):** `tools/vps/vps-up.sh` reads `$HOME/Developer/Personal/oh-my-pi`, checks `~/.local/bin/.omp-sha` on the VPS against local `HEAD`, caches `pi_natives.linux-x64-modern.node` by `git rev-parse HEAD:packages/natives`, and installs the matching binary to `~/.local/bin/omp`.
