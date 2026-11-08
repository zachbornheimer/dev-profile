# omp extensions

Personal omp behavior is an extension in `~/.omp/agent/extensions/`. The omp repo is not the place for a command or a hide the user wants for themselves. See the decision in `SKILL.md` §1.

## Where it lives

1. `~/.omp/agent/extensions/<name>/index.ts` (or `<name>.ts`) — default export `function (pi: ExtensionAPI)`.
2. A sibling file for the pure rule, with a `bun` test next to it.
3. Nothing else: omp auto-discovers `~/.omp/agent/extensions/` (one level deep; project-scoped: `<repo>/.omp/extensions/`). No `config.yml` entry. Restart omp. The current process will not see the command until then.

`extensions:` in `~/.omp/agent/config.yml` is only an optional way to load a path outside the native directories. Agent-callable tools can live in `~/.omp/agent/tools/`, but go through the `creating-new-tools` skill.

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

`bun test` the pure file from the extension directory. Confirm the omp repo diff does not contain the feature. Do not claim the running omp has the command until a new process has discovered the extension.

## Not this skill's job

A Pi extension is a different harness: do not build that here. Do not replace omp's working row.

## Related

- [omp-seams.md](omp-seams.md) — command registration, the display wrap, and the two extensions to copy. Read it before writing the extension.
- `SKILL.md` §2 — when the change belongs in the omp repo instead: land it as a branch.
