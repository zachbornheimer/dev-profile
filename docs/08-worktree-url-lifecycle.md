# 8. Worktree, dependency, and URL lifecycle

Worktrunk user config is installed as `~/.config/worktrunk/config.toml` (copy of `worktrunk/config.toml`). Tools present: `wt` v0.80.0, cowtree 0.4.0, caddy v2.11.7, portless 0.15.7. Do not run `wt config shell install`. Do not install Claude/Codex/OpenCode plugins. No `[commit.generation]`. Do not run `portless proxy start`, `portless trust`, or `portless service install` from this profile.

## Create / switch

`worktree-path = "{{ repo_path }}/../.worktrees/{{ repo }}-{{ branch | sanitize }}"` matches machine-layout (`~/Developer/<Org>/.worktrees/<repo>-<slug>/`). cowtree remains the temporary APFS clone/compact path (`cowtree compact --all --dry-run` in this repo is the dogfood). Worktrunk complements that; it does not store full copies.

## Ignored files

`[post-start] copy = "wt step copy-ignored"`.

`[step.copy-ignored] exclude = [".venv/", "**/.venv/"]` so uv virtualenvs are regenerated (`uv sync`) instead of copied. Absolute paths inside `.venv/` would break.

Other ecosystem rules still hold:

- `node_modules/`: safe to reflink
- Composer `vendor/`: usually copy or composer install; prefer install if path-sensitive
- `.env`: copy if gitignored and not generated per worktree

`.worktreeinclude` limits the copy. Do not copy `.worktrees/`.

## Processes and URLs

The user does not pick ports. An agent must never fix a collision by killing an unknown process (`kp` in zshrc.local is a human shortcut, not an agent tool). Never `kp`. Never kill listeners.

| Approach                      | When                                                             | Identity                                                                                  |
| ----------------------------- | ---------------------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| Portless                      | Single Node/Vite/React where `portless run` wraps the dev script | `https://<branch>.<repo>.localhost` (worktree prefix automatic)                           |
| Worktrunk `hash_port` + Caddy | Laravel+Vite / multi-service stacks that need named routes       | `http://php.<branch>.<repo>.localhost:8080`, `http://vite.<branch>.<repo>.localhost:8080` |

Copy-paste project configs into a repo as `.config/wt.toml`:

- `worktrunk/node-portless.wt.toml` — `wt step tether -- portless run -- mise run dev`
- `worktrunk/laravel-vite.wt.toml` — tethers `php artisan serve` and vite on distinct `hash_port`s, two Caddy routes on :8080

User config stays path + copy-ignored only. No post-start servers there.

Playwright `baseURL` is the named `.localhost` URL, not the numeric port. Report that URL.

`wt step tether` owns teardown of **that worktree's** process group (the PID Worktrunk started). Laravel `[pre-remove]` deletes the two Caddy route ids. Do not kill whatever is bound to a port.

zq `port claim` stays until a repo drops in a template.

First-run Portless CA/proxy is a human step (`portless trust`, `portless proxy start`). This slice does not start the proxy and does not sudo.

## This slice

Canonical worktree path + copy-ignored excluding venvs. Recipes for Portless (Node) and `hash_port`+Caddy (Laravel+Vite). No sudo. No proxy start. No shell integration install.
