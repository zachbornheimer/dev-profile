# Agent memory baseline (ZYS-10118), slice 1: as-is inventory

Measured 2026-11-20 on one Relay sandbox (linux/x64, OMP build 20261119211213-4530cba) against the shared Neon store.
The Mac (`zacharys-mac-mini`) refused SSH (exit 255, Tailscale `check` policy), so nothing below was observed on the Mac.
Marks: **[M]** measured here, **[S]** read from source, **[I]** inference, **[H]** recovered from archived history. No raw transcripts are quoted.

## 1. What the memory system is

| Part | Finding |
|---|---|
| Selector | `memory.backend: archive`, `archive.retainEveryNTurns: 1` in the OMP agent `config.yml` [M]. |
| Store | Neon Postgres `public.memory_chunks`: 638,773 rows, ids unique; 636,787 `chunk` + 1,986 `fact` [M]. No Hindsight or past.dev service in the path since the 2026-11-04 cutover [H]. |
| Schema | `id, session_path, source, repository, occurred_at, chunk_index, body, tsv, embedding, scope, kind`. No `valid_from/valid_to/superseded_by/status` column [M]. |
| Worker code | Fork `zachbornheimer/oh-my-pi`, branch `feat/archive-memory-backend`, head `3b7375f` (2026-11-13), dir `packages/coding-agent/src/memory-backend/archive/` [S]. The installed binary contains the `archive.firstTurnLimit` setting, so the backend is compiled in [M]. Whether that build was cut from `3b7375f` is NOT verified. |
| Supervision | None separate. Capture is an in-process `ArchiveRetainer` subscribed to `agent_end`; recall is `beforeAgentStartPrompt`; consolidation is a lazy in-process sweep gated by a per-machine stamp file [S]. There is no daemon to restart or to be "down". |
| Kill switches | `memory.backend` (anything but `archive` = off), `archive.autoRetain`, `archive.firstTurnLimit: 0`, `retainEveryNTurns` [S]. Subagents (taskDepth>0) never retain [S]. |

## 2. Hook matrix: configured vs observed

OMP event -> Claude Code name, from `~/.omp/agent/extensions/on*.ts` [S]:

| Claude name | OMP event | Extension | Fired this session [M] |
|---|---|---|---|
| SessionStart | `session_start` | onSessionStart | yes, 2 lines (01:12:42, 01:12:54) |
| UserPromptSubmit | `input`, `before_agent_start` | onUserPromptSubmit | yes, 2 lines (3341 ms, 439 ms) |
| PreToolUse | `tool_call` | onPreToolUse, onToolCall | file present; scope guard is OFF unless `OMP_SCOPE_GUARD=on`; no memory logic |
| PostToolUse(+Failure) | `tool_result` | onPostToolUse(Failure) | yes |
| Stop | `session_stop` | onStop | gates: landed/claim/review + judged rules; no memory logic |
| PreCompact / PostCompact | `session_before_compact` / `session_compact` | onPreCompact / onPostCompact | not exercised (no compaction this run) |
| SessionEnd | `session_shutdown` | onSessionEnd | not exercised |
| SubagentStart/Stop | `session_start` / `session_stop` | onSubagentStart/Stop | not exercised |

Memory is wired in two places, neither a guard:
1. **Archive backend** `beforeAgentStartPrompt`: recall once per session, on the first prompt of at least 24 chars, up to 6 hits, Jev relevance threshold 0.65, 6 s timeout. Later prompts get no automatic recall [S]. A `recall` tool exists for manual calls.
2. **onUserPromptSubmit** `retrieveMemoryShortlist` (extensions/prompts/retrieval.ts) queries the same table each prompt for `suggested_memories` pointers. Observed `memory_ms` 154 and 115; `suggested_memories` was `[]` on both prompts [M].

Intentionally unsupported / absent [S]: no memory check before a tool side effect, none at the next model step, no memory-driven Stop correction. Acceptance 2 (interrupt) therefore has no runtime to test yet; it is a gap, not a failing test.

Defects seen on this Relay sandbox [M]:
- The three symlinks in `~/.omp/agent/extensions/` (`handler-timing.ts`, `agent-checkpoint-publish.ts`, `extension-timeout-repair.ts`) point at `/home/zbornheimer/...` and `/Users/zbornheimer/...`, which do not exist here. Result: `telemetry.jsonl` logs a `hook-error` ("ENOENT ... handler-timing.ts") from `tool-load-check` on every `before_agent_start`. Source: `config/mise.toml:254` `mode = "symlink"` with an absolute home.
- `hooks.toml` still registers `hindsight-codex-{sessionstart,prompt,stop}` (agents=["codex"]) running `~/.hindsight/coding-agents/dist/*.js`; `~/.hindsight` does not exist here and Hindsight Cloud was deleted 2026-11-04 [H]. Also `Brewfile` `uv "hindsight-api"` and `more/codex/config.toml` `[mcp_servers.hindsight]`.

## 3. Capture, indexing, recall, provenance

- Capture is idempotent by construction [S]: chunk id = sha256(session_path, index), `on conflict do nothing`, a cursor read from the store decides what is unwritten, secrets redacted before chunking, injected `<system-context>`/`<memories>` stripped. Replay/duplication on the live path therefore follows from the code; I did not replay a transcript twice [I].
- Row integrity [M]: 0 duplicate `fact` bodies per scope; `count(*) = count(distinct id)`.
- Capture coverage [M, rough]: 305 Relay conversations in `relay_run_archive`, 123 distinct `conv-relay-*` conversations present in `memory_chunks` (about 40%). This session's own path had 0 rows 4 minutes after start, as expected before `agent_end`; not re-checked after.
- Indexing lag [M]: 22,929 of 54,069 `chunk` rows from the last 14 days (42%) have no embedding; they are reachable lexically only. Overall 238,712 of 636,787 chunks (37%).
- Recall latency from this sandbox to Neon [M], `recall` tool, 10 distinct queries: p50 63 ms, p95 213 ms, first (cold) 213 ms. n=10, so p95 is the max. Prompt-submit `memory_ms`: 154, 115.
- Not measured: time from turn to recallable memory, warm/cold on the Mac, injection latency end to end, backend-unavailable behaviour (store errors are swallowed per code [S]; no outage was induced), second worktree, resume, compaction.

## 4. Supersession and scopes (source + store)

- Facts are written by `archiveWriteFact` with id sha256(source, path, body): the same body upserts, a changed body is a new row [S].
- The only merge path is `archiveConsolidateFacts` [S]: all embedded facts, cosine >= 0.86, connected components of 2-8, Haiku merge, identifier check (IPs, resource ids, paths) refuses lossy merges, then the **newest row is overwritten and the older rows are DELETEd**. Consequences: no as-of/history query is possible after a merge; the old rows' ids and `source` are gone (only the newest row's id survives); the identifier guard does not cover plain-language facts.
- The clustering SQL and edge computation carry no `scope` or `repository` partition [S], so facts from different scopes can merge. `scope` values in the store are `global, personal, project, sah, zysys`; `project` (325 facts) is written by neither `archiveScopeOf` nor the `memory_ingest` tool enum [S].
- Consolidation is triggered by a per-machine stamp (`~/.omp/agent/archive-consolidated-at`). On this fresh sandbox the stamp was written at 2026-11-20T01:12:42Z, the same instant as the first `session_start` [M]. Every ephemeral Relay sandbox starts without a stamp, so each one may run a full-store sweep [I]. Fact count was 1,986 before and after my queries; I did not observe a sweep delete anything.
- ZYS-9892 stays a narrow autolearn gap; this is a separate storage-level finding: supersession exists only as destructive merge.

## 5. Prior benchmark (recovered from session history, session `01a1a776`, 2026-11-04 22:18-22:30Z) [H]

Corpus: 4 transcripts, 1,737 chunks; 8 known-answer questions (answer tokens verified present by ripgrep); score = expected token appears in top-5 returned text.

| Engine | top-5 | rank 1 | per query | as-of read |
|---|---|---|---|---|
| Neon tsvector + ts_rank | 4/8 | 1/8 | 110-218 ms | correct |
| past.dev | 3/8 | 2/8 | 377-720 ms | failed |
| Hindsight | 0/8 | 0/8 | 8.6-10.0 s | n/a |
| ripgrep (control) | 6/7 | - | 4.26 s | - |

So the claim "beat Hindsight and past.dev" holds only on top-5 recall and latency at n=8 (past.dev won rank-1). It did not test interrupts, supersession through the active runtime, or memory-off vs memory-on. The scorer and fixture files live in a Mac worktree (`capability-replicas`, branch `feat/neon-memory`) that this sandbox cannot reach; they are not recovered. The query tokens are listed above; the 4 transcript ids are not.

## 6. Acceptance status after slice 1

| Criterion | Status |
|---|---|
| Always on in actual sessions | Partly: Relay/Linux wiring, event map and capture/recall/latency numbers done. Not done: Mac, interactive, second worktree, resume, compaction, backend outage, replay-twice. |
| Interrupt prevents wrong action | Not started; no guard exists to test (section 2). |
| Synthesis/merge/supersession | Source + store audit only; no replay run. Missing semantics named in section 4. |
| Repeatable benchmark | Prior results recovered; fixtures/scorer not; no memory-off comparison run. |

## 7. Follow-ups filed

- ZYS-10119: memory-driven guard (no interrupt runtime exists).
- ZYS-10120: consolidation deletes superseded facts and ignores scope.
- ZYS-10121: dangling absolute-home extension symlinks and dead Hindsight registrations on Relay sandboxes.

Still open under ZYS-10118: Mac observation (blocked by the Tailscale check refusal), fixtures/scorer recovery from the Mac worktree, memory-off comparison, replay tests for acceptance 2 and 3.
