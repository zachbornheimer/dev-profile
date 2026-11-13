---
name: omp-discoverable-tool-driver
description: "When an omp custom tool (~/.omp/agent/tools) is registered but not callable (tool_call refuses, eval says registered-but-unavailable, xd:// has no mounted devices), bridge it with a Bun driver importing the tool's own chain; retire once tool activation is pinned"
---

# omp discoverable tools: registered ≠ callable, driver bridge

## The fact

Custom tools under `~/.omp/agent/tools` declare `loadMode: "discoverable"`. Being **registered** in the session does not mean the model can call them: the tool may be absent from the model-facing active set, in a live session **and** in fresh headless `omp -p` probes. A restart does not fix it, and `--tools=<name>` filters the registry without making the tool directly callable in practice.

Symptoms of the gap, all seen with `learn_from_transcript` (2026-11-09):
- `tool_call` refuses: "omp hosts the tool itself … call it directly."
- Direct call: tool absent from the model's callable list.
- `eval tool.<name>(...)`: "Tool is registered but not available in this session."
- `write xd://<name>`: "No such tool … Mounted devices: (empty)."
- omp-live-tools block: `active_tools_count` small (31) while `registered` is large; the tool missing from picks.

Mechanism: the model-facing set is chosen per session/per turn (`sdk.ts` `initialToolNames`, `prompt-tool-activation.ts` `activeToolNamesForTurn`); suggestion-hook matches name gateway-catalog addresses (`omp/<tool>`) that don't match bare registry keys, so nothing activates the tool. (2026-11-09 later: the active set can also jump 31→422 mid-session, so always re-probe before assuming.)

## The bridge (until activation is pinned)

Do not burn turns probing three transports. If the tool's directory exports its chain as plain TypeScript (most `~/.omp/agent/tools` tools do — check `index.ts` for a `factory: CustomToolFactory` whose `execute` calls an exported async function with an explicit deps object), write a one-off **Bun driver** that imports the chain and constructs the same deps the factory builds.

Pattern that worked for `learn_from_transcript` (`/tmp/run-learn.ts`):
```ts
import { learnFromTranscript, loadPreambles } from "~/.omp/agent/tools/learn_from_transcript/chain.js";
// wire deps exactly as index.ts execute() does:
// agent: ompAgentStep(exec, { cwd, addDirs: [annotatedDirectory(), join(agentDir, "threads")] }),
// atask: execAtask(exec, { cwd, signal }), transcripts: transcriptFilesTurnSource(),
// work (implement): optimizeTooling(settingsOf({ tickets }), { eligible, ports: liveTicketPorts(exec, signal), attempts: liveLedger(), lock: liveLock(), ... })
```
- `exec` = a child_process spawn wrapper matching `Exec` in `optimize_tooling/omp_delegate.ts` (stdout/stderr, killed flag). Use `Promise.withResolvers()`, not executor form.
- Run it backgrounded (`bun /tmp/run-learn.ts`) with notify on exit; the chain's own model steps spawn full `omp -p` child sessions, so runs take tens of minutes to hours.
- Import smoke test first: `bun --print 'import("<chain.js>").then(m => console.log(Object.keys(m)))'`.
- Never start a second run (driver or tool_call) while one is mid-flight: the chain files Linear tickets, so a duplicate double-files.

## Action boundary (retire this skill when…)

The long-term fix is making the tool reliably callable, not the driver: pin it with `tools.xdevAlwaysOn` in `~/.omp/agent/config.yml` (glob patterns; a matching tool stays top-level with its own schema) or fix the suggestion-hook name mismatch (`omp/<tool>` vs bare registry key) so `activeToolNamesForTurn` keeps it. Once `learn_from_transcript` is directly callable in a fresh session — verified by a headless `omp -p` probe actually running it — delete this skill and the driver pattern.
