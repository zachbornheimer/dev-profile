---
name: mise-bootstrap-adopt-launchd-agent
description: Move a hand-written ~/Library/LaunchAgents plist (or Homebrew/cargo-built tool) into the dev-env mise bootstrap so a new Mac gets it from mise bootstrap --apply.
---

# Adopt a LaunchAgent into mise bootstrap (dev-env)

Config lives in `~/Developer/Personal/dev-env/mise.macos.toml` (macOS layer) or `~/.config/mise/config.toml` (personal, dotfiles-tracked). Edit in a worktree (`wt switch -c feat/<slug> --no-cd`), never main.

1. Read the existing plist: `plutil -p ~/Library/LaunchAgents/<x>.plist` (program, args, env, intervals, log paths).
2. Add `[bootstrap.macos.launchd.agents.<name>]` with `program`, `args`, `run_at_load`, `keep_alive`/`start_interval`, `throttle_interval`, `process_type`, `environment`, `stdout_path`/`stderr_path`.
   - Launchd does NOT expand `$HOME`; use `{{ env.HOME }}` in program/args/env. `~` works in log paths and working_directory.
   - `WatchPaths` is not a supported key: poll with `start_interval` instead.
   - mise writes plists as `dev.mise.<name>.plist`; the old hand-written plist must be retired after apply.
3. If the program comes from a brew tap, add `"brew:<tap>/<formula>" = { os = "macos" }` to `[bootstrap.packages]`. If it is built from source, add `[bootstrap.repos."~/path"]` (url, ref) and build it in `[bootstrap.hooks.post-tools]` run (guard with `[ -x bin ] ||`, e.g. `mise exec rust -- cargo install --locked --path ... --root "$HOME/.local"`).
4. Scripts the agent runs: track with `mise dot track <file>` so they sync.
5. Validate: `mise trust .; MISE_ENV=macos mise bootstrap launchd-agents apply --dry-run` and `... repos apply --dry-run`. Commit with a conventional, signed message (`feat(bootstrap): ...`), then `wt merge -y main`.

Pitfall: after several `edit` calls on one file, re-read for the fresh tag before the next patch; a stale-tag refusal earlier silently cost two edits that had to be redone. Check landed state with `grep` on main after merge.
