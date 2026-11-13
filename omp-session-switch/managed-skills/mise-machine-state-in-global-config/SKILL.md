---
name: mise-machine-state-in-global-config
description: "Where per-machine state (pinned tools, brew/mas packages, macOS defaults, launchd agents, repo clones) must live for mise bootstrap --apply to work on a fresh machine, and the pitfalls of moving it out of a project mise.&lt;os&gt;.toml env layer."
---

Use when creating or moving per-machine state in a mise setup: packages, macOS defaults, launchd agents, repo clones, or deciding whether state belongs in a project `mise.<os>.toml` env layer or the global `~/.config/mise/config.toml`.

## Placement rule

`mise.<env>.toml` layers load only through `MISE_ENV` or `.miserc.toml` `auto_env = true` (which adds the OS name as an env). On a fresh machine, `mise bootstrap --apply` runs from the global config root and never cds into a project checkout, so a project `mise.macos.toml`/`mise.linux.toml` never applies there. The global config is the documented home for "this machine's setup" and needs no `mise trust`. Per-OS machine state (pinned tools, brew/mas packages, defaults, launchd agents, repo clones the agents depend on) belongs in `~/.config/mise/config.toml`.

## Moving a project layer into the global config: pitfalls seen 2026-11-09

- Merge `[tools]` and `[bootstrap.packages]` into the global tables; naive append duplicates keys. Decide each collision explicitly (e.g. global `ast-grep = "latest"` vs project pin).
- Duplicate `[bootstrap.macos.launchd.agents.<name>]` or `[dotfiles]` keys are TOML redefine errors. When global already has an equivalent agent or dotfile entry, drop the project copy instead of copying it.
- Relative `source` paths in `[dotfiles]` and `{{ config_root }}` resolve against the declaring config's root. Rewrite to absolute `{{ env.HOME }}/...`, or drop the entry if global already tracks the same path (e.g. kitty as `mode = "track"`).
- Linux reads the global config too: guard OS-specific hooks with `[ "$(uname -s)" = Darwin ] || exit 0`. `brew:`/`mas:` package entries carry `os = "macos"` already; `[bootstrap.repos]` entries have no os guard and will clone on Linux.

## Validation sequence

1. Strict-parse the merged file (e.g. `Bun.TOML.parse` in an eval cell) — catches redefine errors before mise does.
2. `mise bootstrap --dry-run` from `~` (global config root), not from the project checkout.
3. `mise bootstrap macos defaults status` — exit 0 means no preference drift.

Pre-flight gotcha: `--dry-run` aborts with `repos: <path> has local changes` if a declared repo is dirty; reconcile that repo first (see `sync-diverged-local-repos-and-lint-clean-push`).
