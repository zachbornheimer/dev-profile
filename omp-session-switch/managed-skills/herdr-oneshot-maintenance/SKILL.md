---
name: herdr-oneshot-maintenance
description: "Editing or testing ~/.config/herdr/oneshot.sh (herdr and Tern one-shot omp prompts): prompt lifecycle, reap/respawn logic, the Tern backend and plugin, and a fake-herdr smoke test."
---

# herdr/Tern one-shot maintenance

Script: `~/.config/herdr/oneshot.sh` (herdr popup key prefix+!; launchd `com.zach.herdr-oneshot-reaper` runs `--reap` every 1800s). Edit it in place; it is not in a git repo. After any edit keep the exec bit (`chmod +x`).

## Model
- Prompt file `oneshot/prompt-<epoch>-<pid>.md` + `.meta` sidecar (target/model/cwd/mux). Pending = `.md` not `.completed.md`. Completed = renamed + touched; deleted after ONESHOT_TTL_SECONDS untouched.
- A prompt is renamed `.completed.md` only when BOTH hold: omp's pane shows the file was opened (`prompt_opened`: a `<file name="...basename">` block in the pane text; the typed `@path` command line does not match) AND the turn is over (done/idle after working, or after ONESHOT_DONE_GRACE_SECONDS). `/resume` literal prompts have no file, so they launch with opened=1.
- State `oneshot/panes.tsv` rows: active, hash, socket, tab, file, seen-working, started, opened. Old rows lack the last three fields (read as 0). `opened` is sticky. The socket column is the multiplexer: a herdr socket path, or the literal `tern` (then the tab column holds the Tern block id).
- Interactive run order: reap -> respawn_pending -> gum prompts -> launch. `--reap` never respawns.

## Multiplexer backends
`ONESHOT_MUX=herdr|tern` (default herdr) picks where new tabs go. Backend calls live in `pane_info`, `pane_read`, `tab_close`, `ensure_session`, `one_shots_workspace` and `launch`; everything else is shared. `respawn_pending` reads `mux=` from the `.meta` so a prompt returns to the multiplexer it came from.
- herdr: `herdr pane list` JSON gives `agent_status` working|blocked|done|idle|unknown; the `agent` key is absent for a plain shell (omp/ompr failed or exited).
- Tern: no agent status. `tern inspect --json` panes have `omp_session_file` (non-null while omp runs) and `working`; they map to agent=omp and working|idle. Tern addresses a tab by its block id (`tern new tab SESSION --cwd D --keep-open --json` -> `.block`), so block id = pane id = tab id. A new Tern session starts with a shell block; `ensure_session` closes it. Tabs are named with `tern rename`. `tern close` on an already-gone block is fine.
- The launchd reaper is herdr-only; Tern rows are reaped by the housekeeping `finish()` starts (`--respawn` via nohup) on each interactive run.

## Tern plugin and keys
`~/.config/herdr/oneshot-tern-plugin/` (`plugin.toml` + `window.luau`, linked with `tern plugin link`; `tern plugin reload` after edits). It registers commands `plugin.oneshot.prompt|new_tab|next_tab|previous_tab|scratch` and binds them under prefix `ctrl+b>` (`!`, `c`, `]`/`tab`, `[`/`shift+tab`, `t`). `prompt` runs `bash oneshot.sh --tern-open` through `tern.process.run` with ONESHOT_FOCUSED_PANE/ONESHOT_CWD; that splits the focused pane down running the plain gum flow with ONESHOT_MUX=tern, then `tern pip` floats it.
- Tern's default keymap owns `ctrl+space` and `shift+space`, so plugin binds there are dropped (`plugin bind left out: the preset binds these keys` in `~/Library/Logs/Tern/tern.log`). Those two prefixes are bound in `~/Library/Application Support/Tern/settings.json` `keybinds` (user layer wins), pointing at the same `plugin.oneshot.*` actions.
- Tern config is `settings.json` + Luau plugins; there is no herdr-style config.toml. Plugin binds are only added, never override defaults.
- Plugin processes start with a bare PATH; the script prepends `~/.local/bin`, mise shims and `/opt/homebrew/bin` so tern, gum and jq resolve.

## Pitfalls
- `[ x = done ]` inside `{ ...; }` needs the `;` before `}`; shellcheck SC1010 flags bare `done` in conditions, so use a `case` on the status instead.
- Tab-separated `read` collapses empty fields: always write explicit 0/1 placeholders in state rows.
- The housekeeping EXIT trap runs after the function returns, so the lock path must be a global (`HK_LOCK`), not a `local`; a local gave `lock: unbound variable` in reaper.log and left `oneshot/.housekeeping.lock` behind (blocks housekeeping until it is 30 min old; `rmdir` it if stale).
- `tern ctl key` from a Tern pane does NOT reach a test pane: it targets the window's focused element (the user's pane) and hangs the calling command. Never use it to press chords; test the script entry points instead.
- edit_patch hunks need a `+` row; a pure-deletion hunk is refused.

## Smoke tests
- herdr, without real herdr: set `HERDR_BIN_PATH` to a stub that logs args to `$FAKE/log` and answers `workspace list`, `pane list` (fixture JSON), `pane read` (emit a `<file name="PATH">` line for panes that should count as opened), `tab create` (returns tab_id/root_pane.pane_id). Set `ONESHOT_DIR` to a temp dir, seed prompt files, meta, rows and stale `.completed.md` (use `touch -t`), run with `ONESHOT_PROMPT/IS_ONE_SHOT/TARGET/MODEL` set to skip gum, then check files, panes.tsv and the log. `bash oneshot.sh --reap` is safe against the real server.
- Tern, real: `ONESHOT_MUX=tern ONESHOT_PROMPT=/resume ONESHOT_IS_ONE_SHOT=yes ONESHOT_TARGET=local ONESHOT_MODEL= ONESHOT_DIR=/tmp/x bash oneshot.sh` opens a tab in the `one-shots` Tern session running `omp /resume`; then `--reap` with the same ONESHOT_DIR. `tern close` the block and `rm -rf` the temp dir afterwards. `--tern-open` with `ONESHOT_FOCUSED_PANE=<block>` under `env -i PATH=/usr/bin:/bin` proves the plugin-style environment; close the popup pane after.
