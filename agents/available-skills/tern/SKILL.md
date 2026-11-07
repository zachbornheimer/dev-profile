---
name: tern
description: >
  Drive Tern, the Stencil multiplexing terminal (same makers as omp).
  Use this whenever the user mentions Tern, a Tern pane, TERN_PANE, or
  wants a command, file, split, or browser shown in the terminal they
  are using, and whenever this session is already inside Tern and the
  user should see the work. Do not use it only because a task could
  use a background shell: run_command owns that. Do not drive Herdr
  when this session is inside Tern.
---

# Tern

Tern is the terminal. Sessions live in a daemon, so a block keeps running after its window closes, and every window shows the same sessions live. A block is a shell, a file, a browser, or a plugin surface. The `tern` CLI scripts those sessions.

The installed binary is the authority. `tern --help` and `tern COMMAND --help` beat this skill when they disagree. Checked against tern 0.9.12 (e498b49).

Stencil's script language (`tern ctl`, `tern shot`, `tern serve`, documented at <https://docs.stencil.so/tern/scripts/>) drives the UI for screenshots and plugin tests. It is not how you run the user's work. Use the session commands below.

## When this applies

Use Tern when the user named it, or when `TERN_PANE` is set and they should see a command, a file, or a split.

Do not open a Tern block just to run a command nobody is watching. `run_command` owns that.

If `TERN_PANE` is set, you are inside Tern. Do not drive Herdr. `run_command` may still drop an interactive command into a Herdr tab when Herdr is installed, which opens the wrong app. Start anything the user should see with `tern new tab`.

If `TERN_PANE` is unset, the CLI can still reach a running daemon. Do not list, split, or close their sessions unless they asked. Say you are not in a Tern pane and stop.

`run_command` usually inherits `TERN_PANE`. If it does not, discover your block from `tern inspect --json` by matching `omp_session_file` to this session. Do not guess `@focused`.

## Your block

```bash
printf '%s\n' "$TERN_PANE" "$TERN_WINDOW_KEY"
tern whoami --json
```

`$TERN_PANE` is your block id. `whoami` is who is at the keyboard, not the pane id. Block ids are large integers. Quote them.

`@focused` is not you. Several tabs each report a focused block, and the window's focus can be the user's tab. Target `$TERN_PANE`, or an id you just read from `--json`.

Commands act on one window: `--window KEY` if you pass it, else the window that holds `$TERN_PANE`, else `$TERN_WINDOW_KEY`, else the first window. The first window's key is empty (`--window ""`). Stay on your window.

## Read state before you change it

```bash
tern ls --json
tern inspect --json
tern process "$TERN_PANE" --json
```

`ls` is sessions, tabs, and blocks. `inspect` adds `panes` and `clients`. A block id and a pane id are the same number.

On a pane, these fields decide what you may touch:

- `working`: Tern thinks an omp turn is in progress. Do not type into that pane.
- `omp_session_file`: that pane's omp transcript. Another omp lives there. Reach it with omp's `agent://` intercom, not by typing into its shell.
- `quiet_ms`: milliseconds since output. Not proof a command finished.
- `exited`: the program has ended. `null` means it has not.
- `cwd`: the block's directory. macOS may show `/tmp` here and `/private/tmp` in `process`. Compare with `realpath`.

`process` on a live shell has `child`, `group`, and `foreground`. On an exited keep-open block those are null. If `foreground` is not the shell, something else is in front. Do not `tern run` into it.

A title, a program name, or `SESSION/BLOCK` also selects a block. Titles and program names collide (`zsh` is every shell). Read the id from JSON and use that.

## Show work in a new tab

A new tab does not take the shown tab, and it does not change the pane you are in. A split does change that tab's layout, which they see when they come back. Default to a new tab. Split only when they asked for a block beside another one.

```bash
tern new tab --cwd "$PWD" --keep-open --json -- <command>
```

The reply is `{"session","tab","block"}`. Use `block` for every later command.

`--keep-open` is required when you need the output. A block whose program exits 0 closes, and the output goes with it. `--keep-open` leaves the block so you can capture it. Do not pass `--end-on-success`. That ends the whole session on status 0 and sends the window back to the previous session.

No command starts an interactive shell in `--cwd`:

```bash
tern new tab --cwd "$PWD" --json
```

Name the tab so they can find it. `rename` names that block's tab (or a session, if you pass a session). Do not rename their session.

```bash
tern rename <block> "short task name" --json
```

`tern focus <block>` switches the window onto that block. Do that only when they asked to look at it. Creating the tab is enough.

## Wait, then read

`tern new tab -- <command>` starts the program. It does not wait.

```bash
tern wait <block> --until exit --timeout 120 --json
tern capture <block> --scrollback
```

`wait` exits with the program's status. Exit 1 with `"status": 1` means the program failed, not that the CLI broke. Exit 124 is the timeout. A timeout does not mean the command never started. Capture before you run it again.

`--until prompt` waits until a shell is back at its prompt. Use that after `tern run`, not after a block whose own program is the command. `--until idle=MS` waits until the block has been quiet for that many milliseconds. Prefer `exit` when you started the program as the block.

`capture` prints the viewport. `--scrollback` includes history, including after a keep-open program has exited. `--ansi` or `--html` when color is the evidence. `--surfaces` adds surface text, which is how an omp conversation rendered in the pane shows up. Use it when plain capture misses the conversation.

Close the block when you are done and they do not need it:

```bash
tern close <block> --json
```

Only close a block you created. `close` returns `{"block": id}`.

## Typing into a shell

`tern run <block> <command>` types the command and Enter into an existing shell. It does not wait, and it types into whatever is in front, including the user's prompt or another agent.

Use it only on a shell you created, after `process` shows the shell in the foreground and `working` is false. Then wait for the prompt and capture.

```bash
tern run <block> git status
tern wait <block> --until prompt --timeout 30 --json
tern capture <block> --scrollback
```

`tern send` is for keys, not for a normal command. `text` and `paste` do not press Enter. `run` does.

```bash
tern send <block> keys ctrl+c
tern send <block> paste "$long_text"
```

Do not send keys to `$TERN_PANE` to drive yourself, and do not send them to a pane whose `working` is true.

## Files

`tern open` shows files in file blocks. A file already open is focused instead, unless you ask for a new block.

```bash
tern open --preview path/to/file:120
tern open --split right path/to/file:120:1
tern open --tab path/to/file
```

`--preview` keeps focus. Use it when you are pointing at a line, not handing them an editor. `--wait` blocks until the blocks you opened close: exit 0 if each was saved or clean, 1 if unsaved changes were discarded. That is for `EDITOR`, not for a glance. With no Tern running, `tern open` starts one.

## Layout they asked for

`tern split <block> right|down --cwd "$PWD" --keep-open --json -- <command>` puts a block beside that block and returns the same `session` / `tab` / `block` object. It changes that tab's splits. Do not split `$TERN_PANE` unless they asked to see it beside this pane.

`tern move`, `tern pip`, and `tern dock` rearrange blocks. Same rule: only blocks you created, and only when they asked. `pip` floats a block. `dock` puts a picture-in-picture back into the split.

## Browser blocks

Only when they asked to open or drive a page in Tern. Read `references/browser.md`, then `tern browser --help`. A browser op can click and submit on a live site. Do not invent a URL they did not name.

## Leave these alone

Run these only when they asked, in those words:

- `tern restart` restarts Tern and the daemon. Programs keep running. It does not unstick a command.
- `tern kill session` ends a session and its programs.
- `tern daemon`, `tern remote`, `tern web serve`, `tern register`, `tern unregister`
- `tern plugin install`, `remove`, `link`, `unlink`. `tern plugin list --json` is fine.
- `tern events` streams JSON until interrupted. Do not run it in the foreground of a turn. `wait` is the completion signal.
- `tern ssh` is how Tern's own shells ssh, including copying terminfo. It is not a general ssh replacement.

The two mistakes that interrupt them are `tern close` on a block you did not create, and `tern focus` when they did not ask to switch. Creating a tab does neither.

## Another omp pane

Panes in `tern inspect --json` with `omp_session_file` set are omp sessions. `working: true` means that turn is still going. Leave them alone. If you need that agent, use `agent://<id>`, not `tern run`.

Your own pane is `$TERN_PANE`. Do not close it. Do not `tern run` into it.
