---
name: omp-startup-profiling
description: "Use when investigating omp startup latency, \"MCP blocks startup\", slow first paint, or status line appearing late; also when editing files in a wt worktree of oh-my-pi from a session whose cwd is the main checkout."
---

# omp startup profiling (measured 2026-11-09, session 01a1c114)

## Findings already established (do not re-derive)
- MCP discovery is ALREADY deferred for UI sessions: `packages/coding-agent/src/sdk.ts` `deferMCPDiscoveryForUI` (hasUI set at `main.ts` ~2394), started by `startDeferredMCPDiscovery(session)` after the session exists. No MCP span appears in the pre-TUI `PI_TIMING` tree. "MCP blocks startup" is not supported.
- Pre-first-frame cost (~4s) = `loadCustomTools` (~1.5-2.0s; 138 modules in `~/.omp/agent/tools`, import time sums ~1.9s, factories ~50ms total) + on the installed assembled build `sessionManager` (~2s, SQL/Neon via `SESSIONS_DB_URL`, `session-storage-env.ts` -> `SqlSessionStorage.create` does CREATE TABLE + ALTER + loadIndex of all rows before first paint). Source tree off origin/main showed sessionManager at only 4-340ms; reason not found.
- Parallelising tool imports in `CustomToolLoader.load` (import all, bind factories in order) gave NO gain (CPU-bound); reverted. Don't retry.
- Post-paint: discover -> connected ~1s, `refreshMCPTools` ~0.1s sync. Status-line segments (model/cwd/branch) are absent from the first full main-TUI frame and appear in the same write as "Connected to MCP server". No MCP gate found in `status-line-host.ts` / `interactive-mode.ts`; cause UNPROVEN.
- Open candidate patches: (1) overlap SQL session init with loadCustomTools (network vs CPU), (2) defer custom-tool imports past first paint, (3) find the status-line gate.

## How to profile
- Pre-TUI tree: `PI_TIMING=x timeout 80 script -q /tmp/t.txt omp </dev/null`, strip ANSI with sed, read the tree (`x` exits after printing, before runInteractiveMode). Works from source with `bun packages/coding-agent/src/cli.ts`.
- Post-paint timeline: Python `pty.fork()` harness (set winsize 50x160), timestamp each read chunk, strip ANSI, search for `Tip:`, `Connecting to MCP`, `Connected to MCP`, `Sonnet 5.5`. TUI uses diff rendering, so only a full repaint proves a row's absence. Kill with SIGKILL; SIGTERM/Ctrl-C can hang and leave a stray `bun` (kill -9 it). `bun --cpu-prof` produced no file this way.
- Event-loop lag: temp `setInterval(10ms)` + `appendFileSync` marks in the deferred block of sdk.ts. Revert afterwards. Caveat: the first lag covers the rest of startup (InteractiveMode construct), not MCP.
- Machine timings can be noisy; run each variant 2-3x and compare relations, not absolutes. Do not report load numbers to the user.

## Gotchas
- `edit`/`write` with RELATIVE paths resolve against the session cwd (the main checkout, on a feature branch). The auto-fork-to-worktree guard only fires for main/master, so a feature-branch checkout gets edited in place. When working in a `wt` worktree (`~/Developer/Personal/.worktrees/oh-my-pi-<slug>`), use ABSOLUTE worktree paths and verify with `git status` in both trees. Line numbers differ between the feature branch and origin/main.
- New worktree needs `bun install --frozen-lockfile` (fast). Native-version mismatch warning is harmless for profiling.
- `wt switch -c` on this partial clone (blob:none) can take >20s and gets promoted to a background job; wait for it.
- Run commands with `run_command` only; `sed -i` and python file writes inside it are denied (use edit/write).
