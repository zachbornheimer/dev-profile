---
name: mise-macos-state-lives-in-global-config
description: "Where macOS bootstrap state (defaults, brew/mas packages, launchd agents, repos) lives for Zach's new-Mac setup, and merge gotchas when editing ~/.config/mise/config.toml"
---

- macOS machine state lives in `~/.config/mise/config.toml` (moved from dev-env `mise.macos.toml`, commit 645ee03, 2026-11-09). A project-local `mise.macos.toml` only loads via `.miserc.toml` `auto_env` after cd + `mise trust`, so a fresh-Mac `mise bootstrap` never applied it. Global needs no trust and already clones dev-env/dev-profile.
- Merge gotchas: TOML forbids redefining a table/key across the file. Check for existing `[dotfiles]` entries (kitty is already `mode = "track"`), `weekly-wt-prune`, `[tools]` keys (`ast-grep = "latest"`), and `[bootstrap.packages]` before appending. Validate with `Bun.TOML.parse` in the js eval (Python eval may be unavailable/probe-timeout).
- `[bootstrap.repos]` has no known `os` guard; guard hooks with `[ "$(uname -s)" = Darwin ] || exit 0` since the global config is also read on Linux.
- `mise bootstrap --dry-run` aborts if `~/Developer/Personal/dev-profile` has uncommitted changes; clean it first to validate the full plan.
- Commits in dev-env run slow hooks (several minutes when the machine is busy): run `git commit` + `wt merge -y main` as a background job and `wait`; do not re-run while one is pending.
- Don't report machine load to the user (rule no-unprompted-load-reports).
