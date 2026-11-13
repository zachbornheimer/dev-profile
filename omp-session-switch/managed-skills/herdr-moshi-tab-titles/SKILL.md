---
name: herdr-moshi-tab-titles
description: "When Moshi shows numbered or clipped Oh My Pi tabs, or the inbox is missing sessions. Herdr tab labels are what Moshi lists; this machine already copies terminal titles onto them."
---

# Herdr tab titles for Moshi

Moshi's workspace list shows Herdr **tab labels**, not the title Oh My Pi draws in the terminal. Oh My Pi writes that title as an OSC sequence. Herdr stores it on the pane (`terminal_title` / `terminal_title_stripped`) and leaves the tab label as a number or a clipped first prompt unless something copies it.

The inbox is a different list. A row appears only after `moshi-hook` forwards a session event. Idle tabs never appear. `no push token registered` in `~/Library/Application Support/Moshi/hook.log` means the phone dropped those events. Pro is not the limit. `transcript not found` means the SSH tunnel dropped; Chat View has no local copy.

## What already runs

- `~/.config/herdr/sync-tab-titles.py` copies each agent pane's terminal title onto the pane and its tab. It strips private-use icons (the phone cannot draw them) and a leading `π:`. A path title is a shell, not a session, and is left alone. A split tab follows the focused pane; each pane still gets its own label.
- `~/Library/LaunchAgents/dev.herdr.tab-titles.plist` runs that script every 15 seconds. Also declared as `bootstrap.macos.launchd.agents.herdr-tab-titles` in `~/.config/mise/config.toml`.
- `~/.config/herdr/reload-config.sh` runs `herdr server reload-config` when herdr is up. `[history.reload]` maps `~/.config/herdr/config.toml` to that script, so a mise apply reloads the running server.
- The script, the wrapper, and the plist are tracked dotfiles.

Do not rebuild this. Run the script once to catch up, then `herdr tab list` to confirm labels. A second run must rename nothing.
