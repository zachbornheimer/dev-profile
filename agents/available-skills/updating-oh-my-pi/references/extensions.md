# omp extensions

Personal omp behavior is an extension in `~/.omp/agent/extensions/`. The omp repo is not the place for a command or a hide the user wants for themselves. See the decision in `SKILL.md` §1.

## Where it lives

1. `~/.omp/agent/extensions/<name>/index.ts` (or `<name>.ts`) — default export `function (pi: ExtensionAPI)`.
2. A sibling file for the pure rule, with a `bun` test next to it.
3. Nothing else: omp auto-discovers `~/.omp/agent/extensions/` (one level deep; project-scoped: `<repo>/.omp/extensions/`). No `config.yml` entry. Run `/reload-plugins` (`AgentSession.refreshExtensions()`) to load new or edited extensions in place (unloading old commands, tools, shortcuts, timers, and `pi.events.on` listeners via `session_shutdown` before replaying `session_start`), or set `tools.hotReloadExtensions: true` in `~/.omp/agent/config.yml` (off by default) to auto-reload changed extensions every 2 seconds (deferred until turn end while busy). Only `/restart` when changing omp core or replacing an in-place prototype wrap.

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

`bun test` the pure file from the extension directory. Confirm the omp repo diff does not contain the feature. Do not claim the running omp has the command until `/reload-plugins`, `tools.hotReloadExtensions`, or a new process has loaded the extension.

## Extension standard (the shape to copy)

Exemplar: `~/.omp/agent/extensions/onUserPromptSubmit.ts` (~70 lines) over `hooks/log.ts` (`hook()`), `prompts/*.ts` and `prompts/*.yaml`. Design record: `extensions/prompts/DESIGN.md`. Host-test rules: `extensions/hooks/TESTING.md`. Small rule-based exemplar: `extensions/fallback-shake/{index,rule}.ts`.

Every new or reworked extension follows these rules.

1. **One responsibility, stated in the header comment.** The first block comment says what the file does and names where each other concern lives (logging, guards, prompts, retrieval). If the comment needs "and" twice, split the file.
2. **`install(pi)` declares; it does not plumb.** It lists inputs (events, questions, thresholds) and one `run` body that receives already-resolved values. Guards (nested run, extension-authored event, empty input, slash command), input freezing, lifecycle bridging (`input` to `before_agent_start`), error capture, and the fire log belong in shared middleware (`hook()` in `hooks/log.ts`), never in the extension. Need a new guard or log field? Extend the middleware once.
3. **Typed values, not raw comparisons.** Model answers are probabilities clamped to [0, 1]; compare with a helper (`meetsThreshold(answers.frustration, FRUSTRATION_THRESHOLD)`), never `answers.x >= 0.7`. Thresholds are named exported constants.
4. **Prompts are data.** Model prompts live in `prompts/*.yaml` (ai-question-schema), loaded and executed by `prompts/*.ts`. No prompt text inline in the extension.
5. **Failures are collected, not thrown.** Push to `errors` and continue. A broken log write, helper, or model call never breaks the user's turn. Any hook step that can hang (a subprocess, a model call) runs under `withDeadline` from `hooks/deadline.ts`, below omp's 10 s handler limit.
6. **Never mutate host objects.** `ctx` has getter-only properties and private fields. Extend it with a non-mutating `Proxy` (`withInquiry`) that forwards with `Reflect.get(target, prop, target)`. Wrap `pi.getAllTools()` and `pi.getActiveTools()` in try/catch (an uninitialized runtime throws).
7. **Pure rule beside the wiring.** Decision logic sits in a sibling file (`rule.ts`, `prompts/*.ts`) with no omp imports; `index.ts` only binds events to it.
8. **No hook-name branching in shared code.** Middleware never checks `name`. A hook opts into behavior through the spec: `hook({ prompt: true })` turns on the prompt lifecycle (trailer stripping, ask recording, `input` to `before_agent_start` replay, always-log questions). A new hook that needs different middleware behavior adds a spec option, not a name check.
9. **No duplicate decision bodies.** Stage logic lives once per stage in `hooks/` (`turn_stop.ts` serves both Stop and SubagentStop, `tool_use.ts` serves PreToolUse). Each `onX.ts` is a thin `hook({ name, event, ctx, questions, inquiryInput, run })` call into it; never paste a decision body into a second entry file.
10. **Tests run against the real host contract.** Each extension has a sibling `*.test.ts`. Hook extensions call `runExtensionHostContractSuite` from `hooks/harness.ts` (initialized, uninitialized, staged-reload) and, for prompt hooks, `simulateInteractiveTurn` and `simulateHeadlessTurn`. Assert behavior and structure, not exact wording. Tests never write production state: `extensions/bunfig.toml` preloads `hooks/test_sandbox.ts`, which sets `OMP_HOOKS_LOG_DIR` and `OMP_HOOKS_STATE_DIR` to a temp dir before any module loads. A new path the extension writes under `~/.local/state` or `~/.agents` MUST honor an override variable like these, and a folder that cannot import `hooks/log.ts` reads the variable itself.
11. **Self-contained.** No imports from `@zab-ai/*`, `@mastra/*` or `capability-replicas` (deprecated).
12. **Prove the load.** `bun test` the sibling files, then `/reload-plugins` or a new process before claiming the running omp has the behavior. For hooks, read the fire log (`~/.local/state/omp-hooks/<hook>.jsonl`) from a real turn.

Automated enforcement: run `bun test hooks/self_contained.test.ts` from `~/.omp/agent/extensions`. The suite rejects symlinks, relative imports outside an extension's folder, and static or dynamic `@zab-ai/*` and `@mastra/*` module specifiers. It also requires each extension entry file to open with a comment or document its default export. That last check proves a comment exists; whether it states one responsibility remains a review check. The suite does not enforce every rule above.

Checklist before calling an extension done: header comment names one responsibility; `install` has no guard, log or lifecycle code; thresholds go through typed helpers; prompts are YAML; no host mutation; pure rule file plus test; host-contract suite passes; load proven.

## Not this skill's job

A Pi extension is a different harness: do not build that here. Do not replace omp's working row.

## Related

- [omp-seams.md](omp-seams.md) — command registration, the display wrap, and the two extensions to copy. Read it before writing the extension.
- `SKILL.md` §2 — when the change belongs in the omp repo instead: land it as a branch.
