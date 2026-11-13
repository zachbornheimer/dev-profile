---
name: dev-env-vps-perf-and-takeover
description: "Working on Zach's dev-env VPS compute arm: omp takeover wrapper, provisioning marker, warm gate, poll loops, and testing/landing gotchas."
---

# dev-env VPS compute arm: facts and gotchas

## Where things live
- `omp()` takeover wrapper: `~/.config/zsh/vps.zsh` (dot-managed; `mise dot save && mise dot sync` commits it). Prints `[omp] taking over session ... from remote compute arm...` when Neon's `omp_session_files` row has a newer mtime than the local file. It then pulls the transcript, ssh-kills the remote omp, rsyncs only the cwd back (gated by `vps_syncable` in `tools/vps/sync-scope.sh`), and scales the box down if idle. Full multi-root sync is `vps:takeback`, not the wrapper.
- Outbound: `ompr` / `vps:continue` (mise.toml) with `tools/vps/pick-session.ts`.
- Provisioning marker: `tools/vps/provision-marker.sh` (v2 hashes only `tools/vps`, `security/rules/typescript.yml`, the neovim pin, dev-profile HEAD). `vps-warm.sh` and `vps-up.sh` compare it with the box's `~/.local/state/dev-env/provisioned`. `VPS_FORCE_PROVISION=1` forces a full run.
- `~/.ssh/config` is NOT under `mise dot`; edits there have no commit.

## Test gotchas
- Tests that call `provision-marker.sh` must set `PATH=/usr/bin:/bin:/usr/sbin:/sbin`; a mise shim ahead of it reads the untrusted `~/.config/mise/config.local.toml` and the marker comes back empty.
- `mise run lint` / `ci` fail on darwin/arm64 because `aqua:denisidoro/navi` and `aqua:upx/upx` are linux-only. That is environmental. Use `MISE_AUTO_INSTALL=false MISE_ENV=security mise tasks deps ci` to inspect the graph; `test:foxguard` lives in `mise.security.toml`.
- `wt step commit` or `git commit` through hk can flip the exec bit; check `git ls-tree HEAD tools/vps/*.sh` against main.
- To smoke-test the wrapper's bun script: extract it and run `bun -e "$code" <sid> <cwd>` (argv indexing differs from `bun file`). When faking a stale local transcript, stash the file with `mv` and restore it with `touch -r`; never `touch -t` a live session file.

## Landing
- Work in a worktrunk worktree (`wt switch -c perf/<slug> --no-cd`), commit, `wt merge -y main`. Commit message must match conventional format, header at most 60 chars.
