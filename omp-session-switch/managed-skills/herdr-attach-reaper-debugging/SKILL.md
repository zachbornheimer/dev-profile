---
name: herdr-attach-reaper-debugging
description: "Debug or modify the herdr blank-shell reaper (~/.config/herdr/reap-blank-shells.py, launchd dev.herdr.reap-blank-shells) when attach does not reap idle zsh panes"
---

# Herdr attach-triggered reaper

Setup: `~/.config/herdr/reap-blank-shells.py` runs resident under launchd (`dev.herdr.reap-blank-shells`, plist in `~/Library/LaunchAgents`, log `/tmp/herdr-reap-blank-shells.log`). herdr has no attach hook, so the script polls `ps` for new `herdr` / `herdr session attach NAME` / `herdr --session NAME` client processes and reaps that session (ctrl+d to idle zsh panes).

Reap criteria: no agent, shell is the foreground process, no non-starship/zsh children, last non-blank screen line is the bare `❯` prompt. Old output above does not protect a pane.

Manual: `reap-blank-shells.py --dry-run SESSION` / `--now SESSION`.

## Pitfalls found
- Always pass `--session NAME` and strip `HERDR_SOCKET_PATH`/`HERDR_SESSION` from the child env; inside a pane or launchd they pin every call to one session.
- launchd daemon-class jobs get background scheduling: every spawned child (`lsof`, `pgrep`) took seconds, so a 123-pane reap never finished. Fix: plist `ProcessType=Interactive`, one `ps -axo ppid=,comm=` snapshot per reap, ThreadPoolExecutor (12 workers) for per-pane herdr calls.
- Never use `lsof` for server uptime; use `os.stat(socket).st_birthtime` (socket is re-created on each server start).
- Test without a real attach: `bash -c 'exec -a "herdr session attach NAME" /bin/sleep 25' &` then read the log. A restart of the job after editing: `launchctl kickstart -k gui/$(id -u)/dev.herdr.reap-blank-shells` (use bootout/bootstrap after plist changes).
- Unresolved: a dry run once said 1 pane for `default` while the daemon then closed 98; cause unexplained.
