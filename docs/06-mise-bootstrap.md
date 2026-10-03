# 6. mise configuration and bootstrap

Live mise: 2026.9.15. Docs used: mise.jdx.dev configuration, bootstrap, deps (2026-09/10). Older zq replacement-guide claiming "no remote include" is stale. Current mise supports `include = ["git::…", "oci::…"]`.

## Phase 1 model

Keep **shims**, not `mise activate`. Parent-directory merge is the profile selector.

1. Global `~/.config/mise/config.toml` remains the base tool pin (chezmoi).
2. `~/Developer/Personal/mise.toml` is a copy of `profiles/personal.toml` (`DEV_PROFILE=personal` only).
3. `mise trust ~/Developer/Personal/mise.toml`.
4. Repo `mise.toml` files stay as they are.

Do not put `[tools]` or one-repo `[env]` in the Personal parent. Over-broad parent config would apply to every Personal checkout including this repo and agentmux.

## `include`

Supported. Trust is the including file's. Untrusted project config will not fetch URLs. Phase 1 copies instead of `git::` so the overlay is local and trusted once.

## `[deps]` (experimental)

`[settings] experimental = true` plus `[deps.npm] auto = true` (or uv/composer providers) can install project packages before `mise run`. Phase 1 does **not** turn this on globally. attention-mail `mise run test` already works without auto-deps. Design may use it later; a working `mise run test` must not depend on it.

## Bootstrap (later, not phase 1)

`mise bootstrap` can converge Homebrew packages, files, repos, dotfiles, shell activation, macOS defaults, LaunchAgents, `[tools]`, then `[tasks.bootstrap]`. Employee onboarding target: install mise, then `mise bootstrap --from <company profile>`. Do not let that requirement shape the Personal overlay.

## Rollback

Delete `~/Developer/Personal/mise.toml`. Revert this repo. zq and zsh unchanged.
