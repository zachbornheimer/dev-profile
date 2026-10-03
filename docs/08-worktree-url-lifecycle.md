# 8. Worktree, dependency, and URL lifecycle

Worktrunk user config is now installed as `~/.config/worktrunk/config.toml` (copy of `worktrunk/config.toml`). Tools present: `wt` v0.80.0, cowtree 0.4.0, caddy. portless absent. Do not run `wt config shell install`. Do not install Claude/Codex/OpenCode plugins. No `[commit.generation]`.

## Create / switch

`worktree-path = "{{ repo_path }}/../.worktrees/{{ repo }}-{{ branch | sanitize }}"` matches machine-layout (`~/Developer/<Org>/.worktrees/<repo>-<slug>/`). cowtree remains the APFS clone/compact path (`cowtree compact --all --dry-run` in this repo is the dogfood). Worktrunk complements that; it does not store full copies.

## Ignored files

`[post-start] copy = "wt step copy-ignored"`.

`[step.copy-ignored] exclude = [".venv/", "**/.venv/"]` so uv virtualenvs are regenerated (`uv sync`) instead of copied. Absolute paths inside `.venv/` would break.

Other ecosystem rules still hold:

- `node_modules/`: safe to reflink
- Composer `vendor/`: usually copy or composer install; prefer install if path-sensitive
- `.env`: copy if gitignored and not generated per worktree

`.worktreeinclude` limits the copy. Do not copy `.worktrees/`.

## Processes and URLs

The user does not pick ports. An agent must never fix a collision by killing an unknown process (`kp` in zshrc.local is a human shortcut, not an agent tool).

| Approach                      | When                                                                        | Identity                                                             |
| ----------------------------- | --------------------------------------------------------------------------- | -------------------------------------------------------------------- |
| Portless                      | Node/Vite/Next-style apps where `portless run` cleanly wraps the dev script | `https://<branch>.<app>.localhost` (worktree prefix automatic)       |
| Worktrunk `hash_port` + Caddy | Multi-service PHP/Vite stacks that need named routes                        | `https://app.<feature>.localhost`, `https://api.<feature>.localhost` |

Playwright `baseURL` is the named URL, not the numeric port.

Worktrunk `[post-start]` can start the dev process; `[pre-remove]` must kill **that worktree's** process tree (the PID Worktrunk started), not whatever is bound to a port.

zq `port claim` stays until Portless or hash_port+Caddy is dogfooded. Those are not this prototype.

## This prototype

Canonical worktree path + copy-ignored excluding venvs. No Portless. No Caddy routing change. No shell integration install.
