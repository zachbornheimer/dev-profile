---
name: omp-hot-reload-setup
description: "Use when configuring, debugging, or extending hot-reload in oh-my-pi (omp) across custom tools, skills, extensions, MCP config, stdio MCP server binaries, or the omp binary itself."
---

# omp Hot-Reload Setup and Architecture

All six live hot-reload surfaces in `omp` share a single session-scoped `HotReloadCoordinator` (`packages/coding-agent/src/session/hot-reload.ts`) and a single unified `hotReload.*` config block in `~/.omp/agent/config.yml`.

## Config (`~/.omp/agent/config.yml`)

The old scattered keys (`tools.hotReload`, `tools.hotReloadExtensions`, `skills.hotReload`, `mcp.hotReload`, `mcp.hotReloadConfig`, `mcp.hotReloadServers`, `session.hotReloadBinary`) have been removed. Use the unified `hotReload` namespace:

```yaml
hotReload:
  enabled: true       # master switch across all subsystems (default: true)
  tools: true         # custom tools (.omp/tools, ~/.omp/agent/tools, provider tools) — default: false
  skills: true        # skills (.omp/skills, ~/.omp/agent/skills, provider skills) — default: false
  extensions: true    # extensions (.omp/extensions, ~/.omp/agent/extensions, local imports) — default: false
  mcpConfig: true     # .mcp.json, mcp.json, and provider MCP configs — default: true
  mcpServers: true    # connected stdio MCP server executables/scripts on disk — default: true
  binary: true        # omp binary on PATH / mise build-latest inside herdr or tmux — default: true
```

## Architecture (`HotReloadCoordinator` + `HotReloadSubsystem`)

- **Coordinator:** `HotReloadCoordinator` (`packages/coding-agent/src/session/hot-reload.ts`) owns the single session poll timer, baseline signature diffing, turn-deferral while `session.isStreaming` is busy (`deferredMessage` deduplicated by `deferralGroup`), and `session.emitNotice` reporting.
- **Built-in subsystems:**
  - `createToolsHotReloadSubsystem` & `createSkillsHotReloadSubsystem` (`src/session/tools-hot-reload.ts`, `deferralGroup: "tools-and-skills"`)
  - `createExtensionsHotReloadSubsystem` (`src/session/extensions-hot-reload.ts`)
  - `createMcpConfigHotReloadSubsystem` & `createMcpServersHotReloadSubsystem` (`src/mcp/config-hot-reload.ts`; `mcpConfigSignature` caches `blake2b256` digests by `(size, mtimeMs, ino)` so idle polls only `stat()`)
  - `createBinaryHotReloadSubsystem` (`src/session/binary-hot-reload.ts`, registered by `InteractiveMode.#startBinaryHotReload` via `session.registerHotReloadSubsystem(...)`)
- **Extension point:** Any caller or embedder can register an additional hot-reload surface on a live session via `session.registerHotReloadSubsystem(subsystem)`.
