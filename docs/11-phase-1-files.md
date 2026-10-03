# 11. Exact files / configs for phase 1

## Created (this repo)

- `~/Developer/Personal/dev-profile/.gitignore`
- `~/Developer/Personal/dev-profile/README.md`
- `~/Developer/Personal/dev-profile/go.mod`
- `~/Developer/Personal/dev-profile/mise.toml`
- `~/Developer/Personal/dev-profile/profile_test.go`
- `~/Developer/Personal/dev-profile/docs/01-tool-ownership.md` … `docs/12-not-rebuilt.md`
- `~/Developer/Personal/dev-profile/profiles/personal.toml`
- `~/Developer/Personal/dev-profile/profiles/base.toml`

## Installed outside the repo (directory selector)

- `~/Developer/Personal/mise.toml` — copy of `profiles/personal.toml` (not a git repo of its own; parent of Personal checkouts)

## Explicitly not in this phase

- `~/.zshrc`, `~/.zshrc.local`, `~/.config/zsh/*`
- any file under `~/Developer/Personal/zq`
- any Software-Automation-Holdings repository policy file (no bulk copy)
- `~/.config/mise/config.toml` / chezmoi mise source (leave AGENTMUX_INSTALL_STRICT leak documented)
- dprint install, Portless, Caddy config, Worktrunk default config
- a new binary on PATH
- `~/Developer/Freelance` or `~/Developer/Company`
- attention-mail `mise.toml` (already has `fmt` and `test`)
