---
name: herdr-popup-key-silent-failure
description: "A herdr prefix key (e.g. prefix+!) that does nothing or flashes closed: diagnose popup command failures (exit 126, lost exec bit) and test the popup command through herdr panes."
---

# herdr popup key does nothing

Gotcha: `[[keys.command]] type = "popup"` in `~/.config/herdr/config.toml` runs the command directly. If the target script lost its exec bit, the popup opens and closes instantly with exit 126 and no visible error. Seen 2026-11-09 with `~/.config/herdr/oneshot.sh` (`prefix+!`), mode was 644.

## Root cause of lost +x (fixed 2026-11-11)
- `writeTextFileAtomically` in `~/.omp/agent/extensions/file-edit/engine/io.ts` and `~/.omp/agent/extensions/zab-ai-tools/kit/tools/hashline/io.ts` (backing `edit`, `edit_replace`, `edit_patch`, `write`, `ast_edit`) previously wrote a sibling `.tmp` file with default `0644` mode and `rename()`d it over the target without preserving `stat(absolute).mode`. Fixed and pinned in `hashline_atomic_write.test.ts`.
- `mise dot` (`mode = "track"`, `encrypt = true`) records the file's `100755` mode inside the `mise-encrypted-file-v1` MsgPack header in `~/.local/state/mise/history/repo.git` (outer Git tree entries for encrypted blobs are `100644` by design).
- Defense in depth: `config.toml:100` (`bash $HOME/.config/herdr/oneshot.sh`), `oneshot.sh:433` (`nohup bash "${BASH_SOURCE[0]}" --respawn`), and the launchd reaper (`/bin/bash`) all invoke through `bash`.

Diagnose:
1. `grep "pane.exit" ~/.config/herdr/herdr-server.log | tail` — `code: 126` (not executable) or 127 (not found) right after the keypress.
2. `ls -l` the script; check shebang and `$HOME` expansion.
3. Test the exact popup command in a real pane (herdr API cannot send keys to the TUI client):
   - `P=$(herdr pane split --current --direction down --cwd /tmp --no-focus | jq -r .result.pane.pane_id)`
   - `herdr pane run $P 'sh -c "bash $HOME/.config/herdr/oneshot.sh"; echo EXIT=$?'`
   - `herdr pane read $P --source visible --lines 30` (expect the gum prompt), `herdr pane send-keys $P esc`, then `herdr pane close $P`.
Notes: `herdr pane process-info` takes `--pane ID`. Binding changes need `herdr server reload-config`. Related: skill herdr-oneshot-maintenance.
