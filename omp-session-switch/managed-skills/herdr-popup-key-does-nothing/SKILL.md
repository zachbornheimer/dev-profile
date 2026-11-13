---
name: herdr-popup-key-does-nothing
description: "A herdr keybinding (e.g. prefix+!) that opens a popup and closes instantly or \"does nothing\": exit 126 cause, bash-prefix fix, and how to test it from inside herdr."
---

# herdr popup key "does nothing"

**Symptom:** a `[[keys.command]]` with `type = "popup"` (e.g. `prefix+!` -> `~/.config/herdr/oneshot.sh`) flashes or never appears.

**Diagnose first:** `grep 'code: 126' ~/.config/herdr/herdr-server.log | tail`. A `pane.exit ... code: 126` per keypress means the script is not executable (`ls -l` shows `-rw-r--r--`). Cause seen 2026-11-09: something rewrote `oneshot.sh` and dropped the exec bit.

**Fix (root, not chmod-only):** invoke the script through its interpreter in `~/.config/herdr/config.toml`: `command = "bash $HOME/.config/herdr/oneshot.sh"`. Then the exec bit is irrelevant. Run `herdr server reload-config`. `chmod +x` is a stopgap that breaks again on the next rewrite. The launchd reaper plist already uses `/bin/bash`.

**Test from inside herdr (cannot send the prefix key via API):** split a pane with `herdr pane split --current --direction down --cwd /tmp --no-focus` (pane id is `.result.pane.pane_id`), `herdr pane run <id> 'sh -c "bash $HOME/.config/herdr/oneshot.sh"; echo EXIT=$?'`, read with `herdr pane read <id> --source visible`, cancel the gum prompt with `herdr pane send-keys <id> esc` (prints "not submitted", EXIT=0), then `herdr pane close <id>`. Do not use `sleep` in run_command; use `herdr pane wait-output`.

**Caveat:** when the machine is overloaded, `herdr` CLI calls can hang past 20s. Use `timeout`, and do not conclude the server is broken from one hang.
