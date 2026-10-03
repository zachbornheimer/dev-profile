# 10. Phased migration and rollback

## Phase 1 (this change)

- Twelve artifacts in this repo
- `profiles/personal.toml` copied to `~/Developer/Personal/mise.toml`
- Tests drive real `mise` from Personal and SAH roots
- Dogfood: attention-mail `mise run fmt` / `mise run test`
- zq stays; zsh stays; no SAH fleet copies; no new CLI

## Later (ordered)

1. Move `AGENTMUX_INSTALL_STRICT` out of global mise and `~/.zshrc` into agentmux
2. Optional `git::` include once this repo has a remote
3. Local trusted dprint exec map + Wasm share; point Personal `mise run fmt` at dprint where it is a win
4. Worktrunk post-create: copy-ignored (except uv venvs) + canonical worktree path
5. Portless or hash_port+Caddy on one Personal app with a durable `dev` task
6. Zsh cleanup: drop duplicate zoxide/PATH/aliases; autoload functions; keep q/* until zq hooks go
7. SAH parent overlay (company policy once, not 70 copies)
8. Employee `mise bootstrap --from <profile>`
9. Remove zq responsibilities that the above made redundant; keep survivors (coordinate, land verdicts, leftover specialized gates)

## Rollback (phase 1)

1. `rm ~/Developer/Personal/mise.toml` (or restore previous absence)
2. `git -C ~/Developer/Personal/dev-profile revert` / reset this commit
3. zq and zsh are untouched, so the previous environment is still there

No Freelance root was created. No Company rename. No zq uninstall.
