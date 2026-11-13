---
name: omp-resume-hang-and-herdr-turn-recovery
description: "Diagnosing and fixing Herdr turn-recovery plugin issues, Herdr plugin runtime gotchas (Permission denied, pane.agent_detected mid-turn firing, local-vs-Neon transcript freshness), and omp remote takeover SSH hangs."
---

# Herdr Turn Recovery & `omp` Resume/Takeover Gotchas

## 1. Ownership: Herdr Turn Recovery (`~/.config/herdr/turn-recovery-plugin`)

Crash-interrupted turn recovery belongs to **Herdr**, not `dev-profile/apps/omp`:
- **Location:** `~/.config/herdr/turn-recovery-plugin` (`herdr-plugin.toml`, `recover.ts`, `recover.test.ts`).
- **Registration:** Linked into Herdr via `herdr plugin link ~/.config/herdr/turn-recovery-plugin` (`~/.config/herdr/plugins.json`) and tracked encrypted via `mise dot` (`"~/.config/herdr/turn-recovery-plugin" = { mode = "track", encrypt = true }`).
- **How it works:**
  - Runs on `[[startup]]` (at 8s and 25s after Herdr server start), `[[events]]` (`pane.agent_detected`), and `[[actions]]` (`sweep` and `dry-run`).
  - Reads the last 256 KiB of the local `.jsonl` file and the last 256 KiB of Neon `omp_session_files` (sharing a single `Bun.SQL` connection across panes), and `pickFresherTranscript` chooses whichever has the newer last entry timestamp.
  - Walks the active branch from `leaf` through `parentId` links (`evaluateTranscript`) to ignore trailing `eval-state-context`, `mode_change`, or normal `session_exit` entries that prevented `omp --restore` from auto-resuming.
  - Sends `herdr agent prompt <pane_id> "."` at most once per `(pane_id, session_path, tailMessageId)` (fenced in `$HERDR_PLUGIN_STATE_DIR/nudged.json`).

## 2. Herdr Plugin Runtime Gotchas

1. **Never rely on `+x` for `command[0]` in `herdr-plugin.toml`:**
   - Herdr spawns plugin commands directly (`Command::new` without a shell). If `command = ["./recover.ts"]` is used and an edit or dotfile sync resets `recover.ts` to `0644`, Herdr fails every hook with `Permission denied (os error 13)` in `herdr plugin log list`.
   - Always invoke via `sh`:
     ```toml
     command = [
       "sh",
       "-c",
       "bun=\"${HOME}/.local/share/mise/installs/bun/latest/bin/bun\"; [ -x \"$bun\" ] || bun=bun; exec \"$bun\" ./recover.ts \"$@\"",
       "recover",
       "--sweep",
     ]
     ```
   - `dev-profile/tests/herdr-plugins-fixture.sh` (run by `tests/doctor.sh`) enforces that every enabled local plugin in `~/.config/herdr/plugins.json` has an executable `command[0]`.

2. **`pane.agent_detected` fires during active turns when foreground child processes exit:**
   - Whenever `omp` runs a foreground tool/command and control returns to `omp`, Herdr logs `agent changed previous_agent=None agent=Some(Omp)` and fires `pane.agent_detected`.
   - `waitForPaneReady` in `recover.ts` must return `"active"` immediately (0 sleep, 0 Neon queries) when `pane.agent_status === "working"` or `"blocked"`, and only poll when `agent_status === "unknown"` or `agent_session` is not yet attached (a newly booting `omp` process).

3. **Always verify Herdr plugins through Herdr's runtime:**
   - Running `bun recover.ts` directly in a shell bypasses Herdr's plugin runner.
   - Verify with:
     ```bash
     ~/.local/share/mise/installs/herdr/latest/herdr plugin action invoke turn-recovery.dry-run </dev/null
     ~/.local/share/mise/installs/herdr/latest/herdr plugin log list </dev/null
     ```
   - Confirm the latest log entry has `"status": "succeeded"` and `"exit_code": 0`.

## 3. `omp` Takeover SSH Hang (`shell/zsh/vps.zsh`)

- Tailscale SSH can pause indefinitely on an interactive browser re-auth check (`To authenticate, visit: https://login.tailscale.com/a/...`), which `ConnectTimeout` does not bound.
- `_omp_probe_remote` in `dev-profile/shell/zsh/vps.zsh` runs the SSH probe with `LogLevel=INFO` and `BatchMode=yes`, auto-opens the Tailscale re-auth URL if printed, and bounds all remote takeover `ssh`/`rsync` calls with `timeout`.
