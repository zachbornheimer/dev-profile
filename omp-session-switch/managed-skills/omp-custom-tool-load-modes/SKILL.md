---
name: omp-custom-tool-load-modes
description: "Setting loadMode/hidden on custom tools in ~/.omp/agent/tools, why extensions/file-edit disables xdev in sdk.ts (upstream vs fork-only), and reaching hidden tools via tool_call or /force"
---

# Custom tool load modes (oh-my-pi fork)

Source (verified, `oh-my-pi-assembled/packages/coding-agent/src`): `ToolLoadMode = "essential" | "discoverable"` only. `"hidden"` is NOT a value (a cast like `"hidden" as "discoverable"` is a silent no-op; an unrecognized value even leaves the tool top-level). The hiding flag is the separate boolean `hidden: true` ("excluded unless explicitly listed in --tools or the agent's tools field"). Use `hidden: true` + `loadMode: "discoverable"`.

## Why `loadMode: "discoverable"` alone does not hide tools in live sessions (verified 2026-11-11)

1. **Startup activation checks `hidden`, not `loadMode` (`sdk.ts:1568, 4642`):**
   - `defaultInactive` is `tool.hidden === true || isDeferredMCPTool(tool)`.
   - `loadMode` (`"essential" | "discoverable"`) is read only inside `if (toolSession.xdev)` (`isMountableUnderXdev` at `sdk.ts:4738`).
2. **`xdev` is disabled whenever an extension wraps `"write"` (upstream bug, `can1357/oh-my-pi` commit `6962d5cd2ef1`):**
   - When `extensions/file-edit` registers `"write"`, `sdk.ts:4015` runs `builtInRegistryToolNames.delete("write")`.
   - `sdk.ts:4159` and `4658` check `builtInRegistryToolNames.has("write")` (ignoring `nativeToolsByName.has("write")` even though `file-edit` delegates `xd://` to `ctx.invokeTool`), so `toolSession.xdev` becomes `undefined` and `loadMode: "discoverable"` is never applied.
   - Upstream fix candidate: check `builtInRegistryToolNames.has("write") || nativeToolsByName.has("write")` at `sdk.ts:4159, 4658`.
3. **Per-turn re-activation (`prompt-tool-activation.ts:10-24, 90`, fork-only commit `5a3c76523a40` on `zachbornheimer/oh-my-pi`):**
   - `ALWAYS_ON_CAPABILITY_NAMES` force-activates the essential names (`read`, `write`, `run_command`, `tool_search`, `skill_search`, `tool_call`) and `extensions/base-tools.ts` (`restrictPayloadTools`) enforces the wire request.

## What `loadMode`/`hidden` cost in each regime

1. **Normal session (`extensions/base-tools.ts`):** `syncBaseTools` sets the active tool list at `session_start` from `ALWAYS_ON_TOOLS` ∪ `CORE_TOOLS` (or `OMP_BASE_TOOLS` when set, enforced on `before_provider_request` via `restrictPayloadTools`).
2. **`OMP_FULL_TOOLSET=1`:** Skips `syncBaseTools`; only tools with `hidden: true` stay out of the startup tool schema.
3. **`--no-extensions`:** Neither `base-tools.ts` nor `file-edit` loads, so `builtInRegistryToolNames.has("write")` stays `true` and `tools.xdev: true` mounts `loadMode: "discoverable"` tools under `xd://`.

## Reaching a hidden/discoverable custom tool

- Put custom tools in `~/.omp/agent/tools/<name>.ts` or `~/.omp/agent/tools/<name>/index.ts` with `hidden: true` and `loadMode: "discoverable"`.
- **Via `tool_call`:** `extensions/prompts/candidates.ts` (`readToolSource`) and `tool_search` (`discoverDiskCustomTools` in `extensions/zab-ai-tools/catalog_ports.ts`) scan `~/.omp/agent/tools/` on disk and emit `tool_call({ address: "omp/<name>", args })`.
- **Via `/force <tool> [prompt]`:** `SessionTools.activateRegisteredToolForForce` (`feat/force-resolve-hidden-tools` in `zachbornheimer/oh-my-pi`, `session-tools.ts:902`) resolves any registered hidden/discoverable tool (exact, hyphen-to-underscore, or `omp/`-prefixed) and activates it at top level for the forced turn; `extensions/base-tools.ts` (`extractForcedToolsFromPayload` + `preserveActive`) keeps it in `payload.tools` across `before_agent_start` and `before_provider_request`, and `print-mode.ts` dispatches `/force` in `omp -p` runs.
- **Gotcha in `DESCRIPTION = [ "..." ].join(" ")`:** `readCustomToolSource` and `readToolSource` extract the first array element using `/["'`]([^"'`]+)["'`]/`. Do not put single quotes (`'`) or backticks inside the first double-quoted string of `DESCRIPTION`, or the catalog description will truncate at that character.
