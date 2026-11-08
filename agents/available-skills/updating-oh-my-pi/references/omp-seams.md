# Seams

Copy these. Do not invent a second way.

## Layout

```text
~/.omp/agent/extensions/<name>/
  index.ts          # default export, patches and commands
  <rule>.ts         # pure decision, no omp imports
  <rule>.test.ts    # bun test
```

Auto-discovered; no `config.yml` entry. Proven extensions: `~/.omp/agent/extensions/hide-evidence`, `~/.omp/agent/extensions/thinking`.

Put tests inside the extension's own subdirectory, never directly in `~/.omp/agent/extensions/`: omp loads every top-level `*.ts`/`*.js` there as an extension (so a top-level `*.test.ts` breaks startup), while in a subdirectory it takes only `index.ts` (or a `package.json` manifest), so `rule.test.ts` beside `index.ts` is safe.

## Command

```ts
import type { ExtensionAPI } from "@oh-my-pi/pi-coding-agent";

export default function name(pi: ExtensionAPI): void {
  pi.registerCommand("name", {
    description: "What the operator sees in autocomplete",
    handler: (args, ctx) => {
      ctx.ui.notify("status line", "info"); // or "warning" | "error"
    },
  });
}
```

`args` is the text after the command name. Empty, `status`, `on`, and `off` are the usual set. Parse them in the pure file.

## Display-only hide

`~/.omp/agent/extensions/hide-evidence/index.ts` wraps `updateContent` and passes a display copy. `~/.omp/agent/extensions/thinking/index.ts` does the same for thinking blocks and short working notes, and wraps tool visibility for `/calm`.

```ts
const updateContent = AssistantMessageComponent.prototype.updateContent;
AssistantMessageComponent.prototype.updateContent = function(message, opts) {
  raw.set(this, message);
  return updateContent.call(this, displayCopy(message), opts);
};
```

`opts.transient === true` means the block is still streaming. A working note stays visible until it settles. A newline, or trimmed length of at least 240, stays. That constant is `CALM_PRESERVE_MIN_CHARS` in `~/.omp/agent/extensions/thinking/display.ts`.

Redraw already-drawn rows only on the user's toggle:

1. Re-call `updateContent` with the stored raw message.
2. `resetStableEmission()` on each captured transcript.
3. `tui.resetDisplay()`.

Capture:

- `TUI.prototype.requestRender` — save `this`.
- `Container.prototype.addChild` — if `"resetStableEmission" in this` and it is a function, save a caller.

Import paths that resolve inside omp:

- `@oh-my-pi/pi-coding-agent` — `ExtensionAPI`
- `@oh-my-pi/pi-tui` — `Container`, `TUI`
- `@oh-my-pi/pi-tui/chat/assistant-message`
- `@oh-my-pi/pi-tui/chat/tool-execution`
- `@oh-my-pi/pi-tui/chat/read-tool-group`

A standalone `bun` import of the entry from `~/.omp/agent/extensions` may fail to load `pi_natives`. That is not a failed extension. omp loads these imports itself. Test the pure file, which imports nothing from omp.

## Other shapes

- `~/.omp/agent/extensions/learn-command.ts` — `registerCommand` only, no drawing.
- `~/.omp/agent/extensions/undo-clear.ts` — `session_start`, `ctx.ui.onTerminalInput`, re-register because omp drops input listeners on `/new` and `/resume`.

## Events

`message_update` and `message_end` carry `event.message`. A step stopped for tools when `content` has a `toolCall`. The TUI often draws the text before tools as its own segment with `stopReason: "stop"` and no tool call. Remember the timestamp from the full message, and treat the first assistant component that then renders that timestamp as the note host. Later segments with the same timestamp are the reply.
