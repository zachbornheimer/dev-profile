# 6. mise configuration and bootstrap

Live mise: 2026.9.15. Docs used: mise.jdx.dev configuration, bootstrap, deps (2026-09/10). Older zq replacement-guide claiming "no remote include" is stale. Current mise supports `include = ["git::…", "oci::…"]`.

## Model

Keep **shims**, not `mise activate`. Parent-directory merge is the profile selector.

1. Global `~/.config/mise/config.toml` remains the base tool pin (chezmoi).
2. `~/Developer/Personal/mise.toml` is a copy of `profiles/personal.toml`.
3. `mise trust ~/Developer/Personal/mise.toml`.
4. Repo `mise.toml` files stay as they are. A child's `[tasks.fmt]` still wins (attention-mail: trunk + ruff).

The Personal overlay now also pins `dprint`, enables experimental mise, and declares `[deps]` auto-providers. Do not put node/python versions or one-repo `[env]` (including `AGENTMUX_INSTALL_STRICT`) in the parent. Global mise and `~/.zshrc` no longer export it; agentmux `.mise.toml` owns it.

## `include`

Supported. Trust is the including file's. Untrusted project config will not fetch URLs. This prototype still copies instead of `git::` so the overlay is local and trusted once.

## `[deps]` (experimental)

`[settings] experimental = true` is on the Personal overlay. Built-in providers enabled there:

- `[deps.aube] auto = true`
- `[deps.uv] auto = true`
- `[deps.composer] auto = true`
- `[deps.go] auto = true`

Do **not** enable `[deps.npm] auto`. Aube is the Node path.

Providers run only when their project inputs exist (uv: `pyproject.toml` + `uv.lock`). In mise 2026.9.15 they bind to the config file's directory, so `mise deps install --list` from `~/Developer/Personal` lists them, and a child with its own `mise.toml` does not re-list the parent providers. The overlay is still in `mise config ls` for every Personal checkout.

## Bootstrap (later)

`mise bootstrap` can converge Homebrew packages, files, repos, dotfiles, shell activation, macOS defaults, LaunchAgents, `[tools]`, then `[tasks.bootstrap]`. Employee onboarding target: install mise, then `mise bootstrap --from <company profile>`. Do not let that requirement shape the Personal overlay.

## Rollback

Delete `~/Developer/Personal/mise.toml`, `~/Developer/Personal/dprint.jsonc`, and `~/.config/worktrunk/config.toml` if this profile created them. Revert this repo. zq and zsh unchanged.
