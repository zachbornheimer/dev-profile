# 8. Worktree, dependency, and URL lifecycle

Phase 1 does not ship Worktrunk/Portless/Caddy as the default UI. Tools already present: `wt` v0.80.0, cowtree 0.4.0, caddy. portless absent.

## Create / switch

Desired: `wt switch --create <name>` at the canonical layout `~/Developer/<Org>/.worktrees/<repo>-<slug>/` (same as `zq worktree` and machine-layout). cowtree remains the APFS clone/compact path (`cowtree compact --all` is already in use). Worktrunk must complement that, not store full copies.

## Ignored files

`wt step copy-ignored` copies gitignored files with copy-on-write reflink when the FS supports it. Default copies all gitignored files except VCS/tool-state/nested worktrees.

Ecosystem rules:

- `node_modules/`: safe to reflink
- uv `.venv/`: **regenerate** (`uv sync`). Virtualenvs often contain absolute paths
- Composer `vendor/`: usually copy or composer install; prefer install if path-sensitive
- `.env`: copy if gitignored and not generated per worktree

`.worktreeinclude` limits the copy. Do not copy `.worktrees/`.

## Processes and URLs

The user does not pick ports. An agent must never fix a collision by killing an unknown process (`kp` in zshrc.local is a human shortcut, not an agent tool).

| Approach | When | Identity |
|----------|------|----------|
| Portless | Node/Vite/Next-style apps where `portless run` cleanly wraps the dev script | `https://<branch>.<app>.localhost` (worktree prefix automatic) |
| Worktrunk `hash_port` + Caddy | Multi-service PHP/Vite stacks that need named routes | `https://app.<feature>.localhost`, `https://api.<feature>.localhost` |

Playwright `baseURL` is the named URL, not the numeric port.

Worktrunk `[post-start]` can start the dev process; `[pre-remove]` must kill **that worktree's** process tree (the PID Worktrunk started), not whatever is bound to a port.

zq `port claim` stays until one of the above is dogfooded.

## Phase 1

No Worktrunk default, no Portless, no Caddy routing change.
