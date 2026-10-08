# 11. Exact files / configs

## Created (this repo)

- `~/Developer/Personal/dev-profile/.gitignore`
- `~/Developer/Personal/dev-profile/README.md`
- `~/Developer/Personal/dev-profile/go.mod`
- `~/Developer/Personal/dev-profile/mise.toml`
- `~/Developer/Personal/dev-profile/profile_test.go`
- `~/Developer/Personal/dev-profile/docs/01-tool-ownership.md` … `docs/12-not-rebuilt.md`
- `~/Developer/Personal/dev-profile/profiles/personal.toml`
- `~/Developer/Personal/dev-profile/profiles/base.toml`
- `~/Developer/Personal/dev-profile/format/personal.jsonc`
- `~/Developer/Personal/dev-profile/worktrunk/config.toml`
- `~/Developer/Personal/dev-profile/worktrunk/node-portless.wt.toml` (copy-paste into a Node repo as `.config/wt.toml`)
- `~/Developer/Personal/dev-profile/worktrunk/laravel-vite.wt.toml` (copy-paste into a Laravel+Vite repo as `.config/wt.toml`)

## Installed outside the repo (directory selector)

- `~/Developer/Personal/mise.toml` — copy of `profiles/personal.toml`
- `~/Developer/Personal/dprint.jsonc` — copy of `format/personal.jsonc`
- `~/.config/worktrunk/config.toml` — copy of `worktrunk/config.toml`

`mise run install-profile` copies all three and trusts the mise overlay.

## Explicitly not in this prototype

- `~/.zshrc`, `~/.zshrc.local`, `~/.config/zsh/*`
- any file under `~/Developer/Personal/zq`
- any Software-Automation-Holdings repository policy file (no bulk copy)
- `~/.config/mise/config.toml` / chezmoi mise source (STRICT leak removed; agentmux `.mise.toml` owns it)
- live `portless proxy start` / `portless trust` / `portless service install` (human; not this profile)
- a Caddyfile in this repo (Laravel routes are the template's admin API on :8080)
- `wt config shell install` or Worktrunk LLM/plugin install
- a new binary on PATH besides the mise-pinned dprint
- `~/Developer/Freelance` or `~/Developer/Company`
- attention-mail `mise.toml` (already has `fmt` and `test`)
