---
name: omp-resume-hang-tailscale-ssh
description: "Use when omp --resume / omp omp:id hangs right after \"[omp] taking over session ... from remote compute arm...\" or ssh to backend.ai.lan.zachandaj.com hangs silently."
---

## Symptom
`omp --resume ...` prints `[omp] taking over session <id> from remote compute arm...` and then sits forever (often across several shells at once).

## Causes (verified 2026-11-11)
1. **Live file is `~/.config/zsh/vps.zsh` (tracked by `mise dot`), NOT `~/Developer/Personal/dev-profile/shell/zsh/vps.zsh`.** `~/.zshrc` sources `~/.config/zsh/loader.zsh`, which loads `~/.config/zsh/vps.zsh`. Editing only `dev-profile/shell/zsh/vps.zsh` leaves active shells running stale code.
2. **Mac-local sessions in Neon false-positived as remote compute-arm sessions:** `~/.config/zsh/05-env.zsh` exports `SESSIONS_DB_URL` on the Mac, so `omp` writes Mac-local turns to `omp_session_files` in Neon without updating `~/.omp/agent/sessions/**/*.jsonl` on local disk. `omp()` in `vps.zsh` previously set `tookOver = true` whenever `diskMtime < Number(r.mtime_ms)` (100% of Mac-local sessions) instead of checking whether the transcript's latest cwd was actually on the Linux compute arm (`/home/...`).
3. **Tailscale SSH check re-auth:** `backend.ai.lan.zachandaj.com` uses Tailscale SSH; when its 12h `"action": "check"` re-auth expires, `ssh` blocks after TCP/SSH handshake on `# Tailscale SSH requires an additional check. To authenticate, visit: https://login.tailscale.com/a/...`. `-o ConnectTimeout=2` does NOT cover this wait.

## Fix in `~/.config/zsh/vps.zsh` (and tested in `~/.config/zsh/tests/vps.test.zsh`)
- Stale rows in `omp_session_files` are still materialized to local disk (`~/.omp/agent/sessions/...`) so `omp --resume` finds them, **but `tookOver = true` is set only when the session's path or latest `current working directory: '...'` (fallback: header `"cwd"`) starts with `/home/` (or `OMP_FORCE_REMOTE_TAKEOVER=1`).**
- When a session truly is on the remote compute arm, `_omp_probe_remote` runs `ssh -o LogLevel=INFO -o BatchMode=yes -o ConnectTimeout=2`, opens any `https://login.tailscale.com/a/...` URL in the browser, kills the probe after 5s if no URL is emitted (or `${OMP_PROBE_TIMEOUT:-30}s` if waiting for browser approval), and bounds all subsequent `ssh`/`rsync` calls with `timeout`.

## If an old shell is still stuck
- Unstick waiting shells: `pkill -f "ssh -o ConnectTimeout=2 backend.ai.lan.zachandaj.com true"`.
- Reload the function in existing shells: `source ~/.config/zsh/vps.zsh` (or `source ~/.zshrc`).
