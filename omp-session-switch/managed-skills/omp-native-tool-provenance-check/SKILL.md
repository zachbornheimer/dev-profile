---
name: omp-native-tool-provenance-check
description: Verify which copy of an omp tool is live (native zab-ai-tools vs omp builtin vs capability-gateway MCP vs standalone ~/.omp/agent/tools) and land changes to that wiring
---

# Checking which copy of a tool omp actually offers

## Check
1. Launch omp in a herdr pane by absolute path with the worktree extension, e.g. `~/.local/bin/omp --model @smol -e <worktree>/mastra/adapters/omp/zab-ai-tools/index.ts` (the zsh `omp` wrapper fails in fresh panes).
2. Send one plain prompt first. Gateway MCP tools connect after session start and the extension hides twins in `before_agent_start`, so a pane that has not completed a turn shows the pre-hide state.
3. Send `/tool-sources` and wait for `RESULT: (PASS|FAIL)`. Rows show tool, active, source, verdict (NATIVE, NOT-NATIVE, MCP-DUPLICATE(x), builtin, mcp) and path.
4. FAIL means a native name is owned by a builtin or another extension, or an active gateway twin remains.

## Facts learned
- omp re-activates every MCP tool on each MCP refresh (`refreshMCPTools` in `session-tools.ts`), so hiding twins once at startup does not hold; `gateway_twins.ts` re-applies it every turn via `setActiveTools`.
- A twin is hidden only while the native tool is registered from a path containing `/zab-ai-tools`; otherwise it stays so no job loses its tool.
- `~/.omp/agent/tools/<name>/index.ts` standalone tools (not in git) shadow kit-core names: find, orient, pin_decision, summarize, system_one, memory_search. They show as NOT-NATIVE.
- Headless `omp -p` does not load ambient extensions, so none of this applies there.
- `run_command` covers `bash` and `bash_status` (background, `jobId` collect, `wait`); only `bash_kill` has no equivalent.

## Landing gotchas
- Never issue parallel edits to the same file with the gateway edit tool: temp-file renames race (ENOENT) and some edits are silently lost. Apply them one at a time and re-check `git diff`.
- A repo hk pre-commit runs oxlint with `--deny-warnings`; an unused variable fails the commit. Do not chain `git commit; git push` with `;` - use `||` to stop, otherwise the push creates a branch with no commits and `gh pr create` fails with "No commits between".
- Landing is push branch, `gh pr create`, `gh pr merge --merge` (never squash, never direct to main).
