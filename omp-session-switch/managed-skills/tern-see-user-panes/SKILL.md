---
name: tern-see-user-panes
description: "Use when the user says \"look in tern\" or asks what they are doing/reading in their terminal: how to list and capture Tern panes from an agent shell"
---

Tern is Zach's multiplexing terminal (`~/.local/bin/tern`). To see what he is doing:

1. `tern ls` lists sessions, tabs and panes as `ID  title  cwd  WxH  [focused]`. Panes titled `omp` are agent sessions; `~` ones are plain shells. An editor pane shows its cwd, not "nvim".
2. `tern capture ID` prints a pane's text (`--scrollback` for history, `--ansi`/`--html` for styling). BLOCK can be an id, `@focused`, a title or a program name; `tern capture nvim` failed with "no block is called nvim", so use the numeric id from `tern ls`.
3. A capture can come back empty (`body: ""`) for an alternate-screen app such as nvim. Try `--surfaces` or `--scrollback`, or fall back to asking which file is open. Do not guess the file from other panes.
4. `tern whoami` only works inside a Tern pane; from an agent shell it errors, which is expected. `tern list` is not a command (use `ls`).

Run these through run_command. They are read-only.
