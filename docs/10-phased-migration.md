# 10. Phased migration and rollback

## Phase 1 (landed)

- Twelve artifacts in this repo
- `profiles/personal.toml` copied to `~/Developer/Personal/mise.toml`
- Tests drive real `mise` from Personal and SAH roots
- Dogfood: attention-mail `mise run fmt` / `mise run test`
- zq stays; zsh stays; no SAH fleet copies; no new CLI

## This prototype (Personal dprint, deps, Worktrunk)

- Overlay adds `[settings] experimental`, `[tools] dprint`, `[deps]` auto for aube/uv/composer/go, parent `[tasks.fmt] = dprint fmt`
- `format/personal.jsonc` copied to `~/Developer/Personal/dprint.jsonc`
- `worktrunk/config.toml` copied to `~/.config/worktrunk/config.toml`
- This repo dogfoods `dprint fmt` / `dprint check`. attention-mail fmt/test unchanged
- `wt config show` sees the canonical worktree-path. `cowtree compact --all --dry-run` in this repo
- Still no Freelance/Company, no zq uninstall, no zsh rewrite, no SAH overlay, no Portless/Caddy

## Later (ordered)

`AGENTMUX_INSTALL_STRICT` is out of global mise and `~/.zshrc` (chezmoi main `ad33364`; agentmux origin/main already had the env).

1. Optional `git::` include once this repo has a remote
2. Portless or hash_port+Caddy on one Personal app with a durable `dev` task
3. Zsh cleanup: drop duplicate zoxide/PATH/aliases; autoload functions; keep q/* until zq hooks go
4. SAH parent overlay (company policy once, not 70 copies)
5. Employee `mise bootstrap --from <profile>`
6. Remove zq responsibilities that the above made redundant; keep survivors (coordinate, land verdicts, leftover specialized gates)

## Rollback

1. `rm ~/Developer/Personal/mise.toml ~/Developer/Personal/dprint.jsonc` (or restore previous absence)
2. `rm ~/.config/worktrunk/config.toml` if this profile created it
3. `git -C ~/Developer/Personal/dev-profile revert` / reset this commit
4. zq and zsh are untouched, so the previous environment is still there

No Freelance root was created. No Company rename. No zq uninstall.
