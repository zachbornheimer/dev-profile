---
name: omp-extension
description: Use when the user wants to extend omp — a slash command, a transcript hide, a presentation toggle, a session hook, or "an omp command" such as /thinking or /calm. Also use when you are about to edit oh-my-pi, packages/coding-agent, or packages/tui to add behavior the user wants for themselves. Personal omp behavior is an extension in ~/.config/omp/, listed in ~/.omp/agent/config.yml. Do not modify the omp repo for that. Not for an explicit omp-source bugfix, and not for a Pi extension.
user-invokable: true
---

# Omp extensions

Personal omp behavior is an extension. The omp repo is not the place for a command or a hide the user wants for themselves.

The failure this prevents: `/thinking` and `/calm` were patched into oh-my-pi. The user wanted `~/.config/omp/`. The installed omp never saw the commands, and the patch folded open tool rows because one apply path did two jobs.

## Decide first

If the user explicitly says to change omp itself, or names an omp bug in the product, edit the repo. Otherwise stop. Do not open `packages/coding-agent` or `packages/tui` to host the feature.

A Pi extension is a different harness. Do not build that here. The user said they will build session progress and activity for Pi separately. Do not replace omp's working row.

## Where it lives

1. `~/.config/omp/<name>/index.ts` — default export `function (pi: ExtensionAPI)`.
2. A sibling file for the pure rule, with a `bun` test next to it.
3. Add the directory to `~/.omp/agent/config.yml`:

```yaml
extensions:
  - ~/.config/omp/<name>
```

A directory that is not listed does not load. `~/.config/omp/` is not scanned. Restart omp. This session's process will not see the command until then.

`~/.omp/agent/extensions/*.ts` is a different pile (learn-command, undo-clear). New personal extensions go in `~/.config/omp/` and get listed, matching hide-evidence and thinking.

## What the extension may change

Drawing and input. Not the message, the model context, or the export.

`AssistantMessageComponent.prototype.updateContent` is the seam every assistant render goes through, including the constructor. Wrap it once. `Symbol.for` on `globalThis` so a reload does not wrap twice. Keep the raw message. Pass a display copy. The session keeps the original.

On the user's toggle, re-call `updateContent` with the stored raw message, then `resetStableEmission` on the transcript and `resetDisplay` on the TUI, so rows already on screen and in scrollback change. Do not `resetDisplay` on every `message_end`. That clears the screen each turn.

Components have no parent pointer. Capture the TUI from `requestRender`. Capture a transcript when `addChild` sees `resetStableEmission`.

Tool shells: wrap `setToolActivityVisible` on `ToolExecutionComponent` and `ReadToolGroupComponent`, and force hidden while the mode is on. Track instances so a toggle reaches rows already drawn. Do not reuse that path for an unrelated toggle. Hiding thinking must not fold tool rows.

Persist next to the extension (`state.json`). Do not add an omp setting.

`pi.registerCommand(name, { description, handler(args, ctx) })`. `ctx.ui.notify` for the status. Parse `on` / `off` / `status` in the pure file and test it.

Events that carry the assistant message: `message_update`, `message_end`. Use them to notice a step that stopped for tools. Do not rewrite the message there.

## Proof

`bun test` the pure file from the extension directory. Confirm the omp repo diff does not contain the feature. Do not claim the running omp has the command until a new process loads the `extensions:` entry.

## Read when implementing

`references/seams.md` — command registration, the display wrap, and the two extensions to copy. Read it before writing the extension. Do not re-derive the seams from the omp repo.
