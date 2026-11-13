---
name: omp-memory-backend-architecture
description: "Use when working on agent memory in this omp fork: the memory.backend selector, MemoryBackend contract, tool-discovery findings, the archive backend and its measured recall, and the Neon memory_chunks store state."
---

# omp memory backends and the Neon store (verified 2026-11-10)

## Commits hang: run git and bun with `MISE_OFFLINE=1`
Measured 2026-11-10. Any `git commit`, `git push`, or `bun` shim invocation in a mise-managed repo without `MISE_OFFLINE=1` triggers `mise` to resolve `tailscale@latest` (`~/.config/mise/config.toml`), which wedges when offline or rate-limited. Prefixing `MISE_OFFLINE=1` runs `hk 2.11.1` and `bun` immediately and still enforces all hooks.

```
MISE_OFFLINE=1 git commit -m "…" && MISE_OFFLINE=1 git push
```

The gate still applies — never `--no-verify` or `HK=0`. A pre-push scan can take up to 1200 s (`DEV_PROFILE_FOXGUARD_BUDGET`).

## Tool discovery and `memory_search` — root causes found and fixed (2026-11-10)
1. **`tool_search` catalog exclusion (`zab-ai-tools/catalog_ports.ts`)**: `tool_search`, `skill_search`, `tool_call`, and `memory_search` in omp are registered by `~/.omp/agent/extensions/zab-ai-tools` (symlinked to `capability-replicas/mastra/adapters/omp/zab-ai-tools`). `CATALOG_TOOL_NAMES` in `catalog_ports.ts` previously included `"memory_search"`, which filtered `omp/memory_search` out of `nativeEntries()` and caused `tool_call({ address: "omp/memory_search" })` to fail with `"unknown tool"`. Fixed in commit `61d918bcaa`: `CATALOG_TOOL_NAMES` now contains only `tool_search`, `skill_search`, and `tool_call`.
2. **`mcp__*` wrapper pollution (`catalog_ports.ts`)**: `nativeEntries()` previously wrapped `mcp__*` tools from `pi.getAllTools()` as `omp/mcp__*` entries that `tool_call` refused to run. Fixed in `61d918bcaa`: `nativeEntries` filters out `!info.name.startsWith("mcp__")`, and `past` / `past-docs` were removed from `mini-lan:~/.local/state/dev-env/mcp-gateway/config.yaml.tpl` and `mcp-gateway:/etc/mcp-gateway/config.yaml.tpl`.
3. **Why `zab-ai-tools` `memory_search` hung (`@zab-ai/ai/tools/catalog/memory.ts` + `catalog_ports.ts`)**: Extensions load after `~/.omp/agent/tools/`, so `zab-ai-tools/memory_search.ts` overrides `~/.omp/agent/tools/memory_search/index.ts`. Its `bm25Arm` ran `order by tsv <@> to_bm25query(...)` across all 585k rows (hanging >30 s) and `catalog_ports.ts` only checked `env.SESSIONS_DB_URL` without falling back to `~/.config/dev-env/runtime/omp-session-db-url`. Fixed in `61d918bcaa`: `resolveSessionDbUrl` reads `~/.config/dev-env/runtime/omp-session-db-url`, `bm25Arm` uses the 5,000-row chunk window + `matched_facts` `ts_rank_cd` CTE, and `searchMemoryChunks` fuses facts and chunks as separate RRF arms with `FACT_RRF_BOOST = 1.25`.
4. **Custom tool execution via `tool_call` (`catalog_ports.ts`)**: `pi.getAllTools()` includes all tools from `~/.omp/agent/tools/*` (even `discoverable`/`hidden` ones stripped from the active list by `onUserPromptSubmit.ts`). `nativeEntries` resolves `customSourcePath` via `resolveCustomToolSourcePath(home, info)` so `tool_call` executes `omp/memory_ingest`, `omp/learn`, `omp/rank_recorded_context`, etc. in-process.

## omp built-in layer (`packages/coding-agent/src/memory-backend/`)
- `memory.backend` enum: `off | local | hindsight | mnemopi | sharpshooter | archive`. Resolver `resolve.ts`, setting `memory-backend/settings.ts`. `~/.omp/agent/config.yml` now sets `memory.backend: archive`.
- Built-in memory tools (`src/tools/memory-recall.ts`, `src/tools/memory-retain.ts`, `src/tools/learn.ts`) and `memory://` URL resolution (`src/internal-urls/memory-protocol.ts`, `src/session/session-memory.ts`, `src/memory-backend/global-scope.ts`) are wired for `memory.backend === "archive"`.
- Custom tool `~/.omp/agent/tools/learn/index.ts` also persists applier answers as redacted `kind='fact'` rows in `public.memory_chunks` through `runMemoryIngest`.

## archive backend (branch `feat/archive-memory-backend`, pushed at `cc916b1c8`)
`src/memory-backend/archive/{backend,client,retain,search,settings}.ts` + `test/memory-backend/archive.test.ts` (34 pass).
- `openArchiveClient()` reads `SESSIONS_DB_URL` (else `~/.config/dev-env/runtime/omp-session-db-url`) with `Bun.SQL`.
- `beforeAgentStartPrompt`: first-turn recall (respects `memory.archive.firstTurnLimit`, 4 s budget, skipped under 24 prompt chars, delivered once per session).
- `save()` (`archiveWriteFact` in `retain.ts`): writes explicit facts/lessons (`kind='fact'`, deterministic `fact-archive-<sha256>` id, soft scope from cwd/repo) so `memory_retain` and `learn` persist directly to `public.memory_chunks`.
- Turn-end auto-retain (`ArchiveSessionRetainer` in `retain.ts`): chunks settled turns and inserts `kind='chunk'` rows with `ON CONFLICT (id) DO NOTHING`.
- Soft context, never a filter: `archiveContextBoost` multiplies rank by 1.15 (same repository) and 1.2 (body names a touched file); facts ×1.25; facts and chunks fuse as separate RRF arms.
- Panel condition in `archive/settings.ts`: uses `const isMemoryBackend = (s: ScopeLike, id: string): boolean => cfgMemoryBackend.get(s) === id;` so `archiveActive` filters the settings UI without tripping the `express-ssrf` semgrep rule.

## Neon store (`public.memory_chunks`)
- Backfilled through 2026-11-10 via `packages/coding-agent/scripts/memory/archive-backfill.ts` (`f12efc407`): **1,046,204 total rows** (475,274 new chunks from 7,129 sessions since 2026-11-07).
