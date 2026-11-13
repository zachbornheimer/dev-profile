---
name: omp-startup-token-audit
description: "Measuring omp startup/prompt tokens and attributing them (tools, context files, system prompt, skills), the audit_startup tool and /audit-startup, per-tool sizes, why headless and interactive numbers differ, herdr OMP_ONE_SHOT probes"
---

# omp startup-token audit

Tool: `~/.omp/agent/tools/audit_startup/` (engine `audit.ts`/`run.ts`, probe extension `probe_extension.ts`, CLI `cli.ts`, tests `audit_startup.test.ts`); slash command `extensions/audit-startup-command.ts` (writes `~/.local/state/omp-hooks/audit-startup.json`; not confirmed live). The tool is `hidden: true` + `loadMode: "discoverable"`: reach it with `tool_call({address:"omp/audit_startup"})`. See skill `omp-custom-tool-load-modes` for what loadMode/hidden really do (in real sessions the extension's tool-set sync already removes it; loadMode only shows under `--no-extensions`).

## How attribution works (measured, not tokenized locally)
Headless `omp -p --mode json` probes; provider usage on the first request is the total. Arms:
- partition (component = default minus arm): `tiny_prompt` (`--system-prompt x` -> `system_prompt`), `no_context_files`, `no_skills`, `no_rules`, `no_lsp`.
- `floor`: all removals at once; left is tool schemas + fixed system text (`<project-context>` wrapper, extension-added blocks) + request messages. Split by the floor request's exact characters.
- `request_dump` and `floor` load `probe_extension.ts` via `env AUDIT_REQUEST_DUMP=<file> omp -e ...`: `before_provider_request` hands it the exact payload (system blocks, messages, every tool JSON). `tools.by_tool[].est_tokens` spreads the measured tool total by characters (~0.39 tokens/char); each row is an estimate.
- `no_extensions` is an overlapping ablation (never summed): it removes the tool-set sync, so it declares a different tool list and adds catalog lines. NOT representative of a real session.
- Components add up to total within `interaction` (about -0.2%).

## Measured 2026-11-10 (haiku-5-5, cwd ~/.omp/agent, 32 tools, default 55,619 tokens)
tool_schemas 31.7k (57%), context_files 14.9k (27%, 48k chars of AGENTS.md chain), system_prompt 4.5k (8%), system_fixed 3.0k (5%), lsp 1.1k (2%), request_messages 0.5k (1%), skills 0, rules 0. Biggest tools: run_command ~4.1k, wait ~3.9k, task ~2.8k, task_fleet ~1.8k, eval ~1.5k. Tools dominate, not skills.
- The 34-name allowlist in `onUserPromptSubmit.ts` (`syncBaseTools`) is the real tool-token lever: `OMP_FULL_TOOLSET=1` gives 188,620 tokens / 168 tools vs 55,620 / 32. Shrinking tool tokens means changing that allowlist (or tool descriptions), not loadMode.
- Not built yet: a "no tool sync" arm (env `OMP_FULL_TOOLSET=1`) so the report shows what the sync saves and gives a real before/after for allowlist changes.

## Gotchas
- `--no-extensions` still loads essential custom tools from ~/.omp/agent/tools, so it declares 13 tools, not 0. `--no-tools --no-extensions` declares ~139; `--tools ""` is ignored. Not usable as a floor.
- Earlier the same default probe gave 246,568 tokens/415 tools vs 52,800/26: MCP readiness. Report flags `comparable:false` / `mcp_not_ready`; use `--repeats`.
- Compare two reports by default total and `tools_declared_names` first; deltas move between components when an arm gains a tool (the Desktop before/after +905 was exactly that).
- run_command refuses `sleep` loops, `find`, `grep -r`, in-place edits and Python that writes files; use `wait`, glob/grep, and the edit/write tools.

## herdr fresh-interactive probe
- `OMP_ONE_SHOT=1 omp --model M '<prompt>'` in a herdr pane answers once then exits. Recipe: `herdr workspace create --cwd D --label X --no-focus` -> workspace_id and root_pane.pane_id; `herdr pane run <pane> "..."`; `herdr pane read`; `herdr workspace close <ws>`.
- A one-turn interactive session never wrote its `.jsonl`, so provider usage is unreadable there; headless probes remain the measurement.
