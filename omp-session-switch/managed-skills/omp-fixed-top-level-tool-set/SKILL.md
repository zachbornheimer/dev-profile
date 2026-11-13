---
name: omp-fixed-top-level-tool-set
description: "Use when configuring or debugging omp's top-level tool set, loadMode ('essential' vs 'discoverable'), tools.xdev / tools.xdevDocs='none', extensions/base-tools.ts, or startup token usage."
---

# omp Fixed Top-Level Tool Set & `loadMode === "essential"`

## Architecture (verified 2026-11-11, `build-20261111174156-38be738-acbc6b8`)

- **Single source of truth (`loadMode === "essential"`):**
  - Only the 6 essential startup tools declare `loadMode: "essential"`: `run_command`, `write`, `read`, `tool_search`, `skill_search`, `tool_call`.
  - Every other tool in `extensions/zab-ai-tools/index.ts`, `extensions/file-edit/index.ts`, and `~/.omp/agent/tools/*` explicitly declares `loadMode: "discoverable"` (and `hidden: true` for custom tools under `~/.omp/agent/tools/*`).
  - **Gotcha (`defaultLoadModeForToolName`):** `packages/coding-agent/src/tools/essential-tools.ts` defaults an omitted `loadMode` to `"essential"` for any tool whose name is in `ESSENTIAL_BUILTIN_TOOL_NAMES` (`read`, `write`, `bash`, `edit`, `glob`, `find`, `eval`, `task`, `autolearn_learn`, `autolearn_manage_skill`, `context_notes`, `new_context`). Therefore, an extension overriding a built-in name (such as `glob` or `find` in `extensions/zab-ai-tools/index.ts`, or `edit` in `extensions/file-edit/index.ts`) MUST explicitly set `tool.loadMode = "discoverable"` when it should not be top-level at startup.
  - **Gotcha (internal `<extension:...>` tools):** Built-in extensions inside the `omp` binary (`autolearn_learn`, `autolearn_manage_skill`) report `sourceInfo.source === "extension"` and `sourceInfo.path === "<extension:...>"`. `isEssentialTool` in `extensions/base-tools.ts` ignores `loadMode: "essential"` on internal tools whose `sourceInfo.path` starts with `"<"`.

- **`tools.xdev: true` and `tools.xdevDocs: "none"` (`~/.omp/agent/config.yml`):**
  - `sdk.ts:4159, 4658` and `session-tools.ts:1430` check `builtInRegistryToolNames.has("write") || nativeToolsByName.has("write")` (and `this.#toolRegistry.has("write")`) so `extensions/file-edit` wrapping `write` does not disable `tools.xdev`.
  - `tools.xdevDocs: "none"` unmounts all `loadMode: "discoverable"` tools into `xd://` without injecting the static `# xd:// Tool Devices` catalog or mounted MCP route list into the system prompt.
  - `prompt-tool-activation.ts` on `assembled` keeps only the 6 essential tools in `ALWAYS_ON_CAPABILITY_NAMES`.

- **Enforcing the startup set across lifecycle events (`extensions/base-tools.ts`):**
  - `syncBaseTools(pi)` runs on `session_start` AND idempotently on `before_agent_start` (so late `mcp-gateway` `refreshMCPTools` calls or hot-reloads cannot re-expand active tools).
  - `restrictPayloadTools` runs on `before_provider_request` so wire requests never include non-essential tools unless `OMP_FULL_TOOLSET=1` is set.
  - When an autoresearch `.db` exists for `process.cwd()`, `EXPERIMENT_TOOLS` (`init_experiment`, `run_experiment`, `log_experiment`, `update_notes`) are added automatically.

## Measured Baseline (autoresearch Run #21 & live `herdr` session, 2026-11-11)

| Arm | Disclosed Tools | Startup Context | Task Tokens | Turns | Search Turns | Wall Time | Pass Rate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `full` (`OMP_FULL_TOOLSET=1`) | 168 | 187.6k | 752,632 | 4.0 | 0.0 | 63.5s | 100% |
| `min` (`tool_search`, `tool_call`, `skill_search`) | 3 | 25.1k | 142,450 | 5.0 | 1.0 | 38.1s | 100% |
| `lean` / live default (6 essential tools) | 6 | 27.9k–28.4k | 117,728 | 4.0 | 0.0 | 22.9s | 100% |
