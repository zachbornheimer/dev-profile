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
| Always on in actual sessions | Partly (section 9): hooks fired on headless Relay/Linux and recall injected without a manual call; helper sessions were captured, but capture of my own probe runs and of this session's later turns is NOT confirmed. Not verified: Mac (SSH refused), interactive TUI, compaction, resume, backend outage. |
| Interrupt prevents wrong action | Opt-in guard merged (ZYS-10119, #221). Replayed with a fake judge 1/0/0/0, and with a real model as judge (section 12): 1/0/0/0 plus one bounded Stop correction, but only with pre-scored states: uncached, a real call exceeds the 2.5 s deadline and the guard fails open (ZYS-10143). Jev precision unmeasured. |
| Synthesis/merge/supersession | Section 8 (old head, destructive) is superseded by section 10: after ZYS-10120 the real SQL on real Postgres keeps history, partitions scopes, and is idempotent. Resurrection window remains. |
| Repeatable benchmark | Prior results recovered and re-run on the live store (section 11); memory-on vs memory-off A/B run on 5 prompts. Original fixtures/scorer (Mac worktree) still not recovered. |

## 7. Follow-ups filed

- ZYS-10119: memory-driven guard (no interrupt runtime exists).
- ZYS-10120: consolidation deletes superseded facts and ignores scope.
- ZYS-10121: dangling absolute-home extension symlinks and dead Hindsight registrations on Relay sandboxes.

Still open under ZYS-10118: Mac observation (blocked by the Tailscale check refusal), fixtures/scorer recovery from the Mac worktree, memory-off comparison, replay tests for acceptance 2 and 3.

## 8. Supersession replay on a scratch store (no shared data touched)

  > Superseded by section 10. Section 8 describes the fork at `3b7375f`, before ZYS-10120 (#91-#93) landed; the test it names pinned the destructive behaviour and stays only as the red baseline.

`docs/design/agent-memory-supersession-replay-zys-10118.test.ts` runs the real `archiveConsolidateFacts` (fork @ `3b7375f`) over an in-memory SQL fake with synthetic facts. 5 tests, 16 expects, all pass. They pin the **current** behaviour, which fails the ticket's semantics:

| Case | Observed |
|---|---|
| Complementary facts + paraphrase + explicit correction | Synthesized into one row (newest id `k1`); both the old and the corrected host stay in the merged body, so current recall still shows the superseded value. |
| As-of / history read | Impossible: older rows are deleted, and their ids and sources are recorded nowhere. |
| Newer similar statement in an unrelated scope (`sah`) | Personal facts fold into the `sah` row; text crosses scopes. |
| Replay twice | No-op (0 clusters on the second run). |
| Out-of-order insertion | Same final store as in-order. |
| Re-ingest of a superseded fact (same id) | The row returns (`on conflict do update` recreates it) until the next sweep: a resurrection window. |

Limits: Haiku is replaced by a join-all-bodies combiner and embeddings are two-dimensional, so merge wording quality and real similarity are not tested; no recall query was run. ZYS-10120 should convert these assertions into the required semantics.

## 9. Always-on on headless Relay OMP, observed (this sandbox, 2026-11-20)

Two `omp -p` runs in a throwaway `--session-dir`, no manual retain or recall:

| Event | OMP name | Fired | Evidence |
|---|---|---|---|
| SessionStart | `session_start` | yes | `onSessionStart.jsonl` +1 per run |
| UserPromptSubmit | `before_agent_start` (not `input`) | yes | `onUserPromptSubmit.jsonl`, `memory_ms` 118-172 |
| PreToolUse / PostToolUse | `tool_call` / `tool_result` | yes | 36 -> 40 lines after one bash call |
| Stop | `session_stop` | yes | `onStop.jsonl`: gates 4/1/9/220 ms, decision allow |
| SessionEnd | `session_shutdown` | yes | `onSessionEnd.jsonl` +1 |
| PreCompact / PostCompact | `session_before_compact` / `session_compact` | not exercised | no compaction reached |

Ordering seen in the trace: SessionStart, UserPromptSubmit, PreToolUse, PostToolUse, Stop (02:07:28.804), SessionEnd (02:07:28.980).

Capture, corrected: I first read rows at 02:07:04-02:07:27 as my probe run's capture. They were not: they are the harness's own helper sessions (turn-waste review, shell-output summarizer) that run in `/tmp`. Searching `public.memory_chunks` for my probe strings (`zys10118-trace-ok`, `zys10118-second-turn`, `capture-probe-zys10118`) found 0 rows, so **capture of my own `omp -p` runs is not confirmed**. What is confirmed: such helper sessions do reach the store as `source=omp`, `scope=personal`, `repository=tmp` within seconds of their last turn, with no manual call, so the `agent_end` subscriber fires on real settled sessions. This Relay session itself holds only its first prompt (5 chunks, 01:12:46); its later turns were not in the store 70 minutes on. Retention is the archive backend's in-process `agent_end` subscriber, not a queue: there is no separate ack or worker to restart.

Not verified: Mac, interactive TUI, compaction, resume/branch, backend outage, a second worktree.

## 10. Supersession replay on real Postgres (fork `f7f3e88`, ZYS-10120 merged)

`docs/design/agent-memory-supersession-pglite-zys-10118.test.ts` runs the real `archiveConsolidateFacts`, `archiveSupersedeFacts` and `archiveFactsAsOf` SQL against PGlite 0.3.14 with pgvector (a real Postgres, throwaway, in memory; no shared data touched). 4 tests, 22 expects, pass. Run: `OMP_FORK=<oh-my-pi checkout at f7f3e88> bun test <file>` with `@electric-sql/pglite` installed.

| Requirement | Result |
|---|---|
| Complementary facts + paraphrase + correction synthesize | one current row (`k1`) holding the config path and the new host |
| Old version retrievable as-of, source ids kept | pass: `archiveFactsAsOf` before the merge returns `c1,c2,k1,p1,t1` with the pre-merge `k1` text and `src-c1`; after the merge only `k1,t1` |
| Unrelated-scope newer fact never merges across scopes | pass: `u1` (sah) unchanged, personal ids merged only among themselves |
| Replay twice, out of order | pass: second run finds 0 clusters, history row count unchanged, reversed insertion gives the identical store |
| Resurrection | **fails the requirement**: re-ingesting superseded `c1` (same id) makes it current again until the next sweep, because the retain upsert has no tombstone check |
| Only the authoritative replacement for current queries | **not met by the storage layer**: the stub combiner (join-all) keeps the old host in the replacement body. Whether the real Haiku combiner resolves it to the newest value was not run |

So supersession exists and is non-destructive for consolidation; the open gaps are a tombstone on re-ingest and a contradiction check on the combiner output. No recall query was run against the superseded set.

## 11. Benchmark: recovered run, re-run, and memory on vs off

**Recovered run** (section 5, 2026-11-04, 4 transcripts, 8 questions). Re-run on the live store today, same 8 answer tokens, `plainto_tsquery` + `ts_rank` over chunks of session `01a1a776`, top-5: 8/8 hit, 8/8 rank 1, 0.77-1.02 s per query from this sandbox (store now holds 1,446 chunks + 217 facts for that session vs 1,737 chunks then). This is an easier question than 2026-11-04's prose questions, so it is not a like-for-like score. The original fixtures and scorer are in a Mac worktree that was unreachable.

**Memory on vs off**, `docs/design/agent-memory-ab-zys-10118.sh`: 5 prompts ("From our earlier work: ...") whose answers exist only as archived facts, same answer model, `omp -p --no-session --no-tools`. Off = `memory.backend: off` plus `--no-extensions` (without `--no-extensions` the prompt hook still recalled: the first off attempt answered from memory, so that arm was discarded).

| | memory on | memory off |
|---|---|---|
| gold token present | 5/5 | 0/5 |
| declined / "no record" | 0/5 | 5/5 |
| wall time mean | 17.2 s | 8.0-20.3 s per prompt (n=5, noisy) |

No wrong answers in either arm. On a fresh Relay sandbox the first run with extensions disabled in the off arm also wrote one junk fact (`memory_ingest` "noop") to the shared store; I deleted that one row by id. Fixture ids are the five prompts in the script; n=5 and one model, so this shows direction, not a rate. Not measured: interrupts, false interrupts, stale injections, rework avoided, time from turn to recallable memory, warm vs cold injection latency (only `memory_ms` 115-172 ms from the prompt hook and recall p50 63 ms / p95 213 ms, section 3).

## 12. Interrupt guard with a real model as judge (2026-11-20)

`docs/design/agent-memory-guard-real-judge-zys-10118.test.ts` drives the shipped guard (`hooks/memory_guard.ts`, `decidePreToolUse` in `hooks/tool_use.ts`, `createMemoryStopGate`) with a real model as judge: `omp -p --no-session --no-tools --no-extensions` asked the same yes/no question as `prompts/memory_conflict.yaml`. This sandbox has no System One / OpenRouter key (all three env vars unset), so this is **not** Jev: it shows the guard's behaviour with a real judge, not Jev's precision. Seeded decision: "this project installs dependencies with bun only; never run npm or pnpm install", repository `dev-profile`. Run: `cd ~/.omp/agent/extensions && bun test <file>`.

| Case | Blocks | Ran | Judge calls | Result |
|---|---|---|---|---|
| conflict: `npm install`, then `bun install` | 1 | `bun install` | 1 | agent revises course; answer streamed once |
| no conflict: `bun install` | 0 | `bun install` | 2 | no interruption (judge scored 0.02) |
| outdated memory (superseded body, 2025) | 0 | `npm install` | 0 | does not steer; judge never reached |
| cross-repo and no-repo memory | 0 | `npm install` | 0 | does not steer; judge never reached |
| conflicting final answer at Stop | 1 | n/a | 1 | one correction; the corrected answer is accepted, no loop |

Real judge scores: `npm install` 0.97, `bun install` 0.02 (against the 0.8 threshold). 6 tests, 9 expects, pass.

**Finding (ZYS-10143, filed and delegated to Relay).** The first run, with nothing cached, failed: the conflicting `npm install` ran (blocks 0). A real judge call took 7.5-9.6 s and `MEMORY_DEADLINE_MS` is 2.5 s, so `withDeadline` cut it off and the guard failed open. The passing run pre-scores each state once without a deadline, so it proves the decision logic and not the deadline. In production the judge is System One, whose `judge_ms` on this sandbox was 276-4692 ms (prompt-hook trace), so the 2.5 s budget can fail open there too. That is a real gap in criterion 2's "in time".

Still not measured: Jev's precision and recall, false interrupts over real traffic, stale injections, rework avoided.

## 13. Capture and outage edges, headless (2026-11-20, supersedes section 9's capture paragraph)

Probes on one Relay sandbox (omp 19.0.0 build 20261119211213-4530cba, `memory.backend: archive`), each a plain `omp -p "Reply with exactly: <unique token>"`:

| Probe | Observed |
|---|---|
| Default session dir, then two with `--session-dir` | Each created a session directory (`changes.jsonl`, `blobs/`, `local/`) but **no `<session>.jsonl`**. A search of `public.memory_chunks` for each token (rows since the run) found 0 rows a minute or more later. Capture of a plain `omp -p` run did not happen. Cause not traced: the retainer returns 0 without a transcript file in the fork source (read at `3b7375f`), which is consistent but unconfirmed. Filed ZYS-10145. |
| Same prompt with `SESSIONS_DB_URL` pointing at a closed port | Exit 1 after about 2 s, `PostgresError: Failed to connect (ERR_POSTGRES_CONNECTION_REFUSED)`, no answer; same with `--no-extensions`. The control answered in 9 s. An unreachable store aborts the headless run instead of degrading. Filed ZYS-10146. |

This corrects section 9: helper sessions in `/tmp` were captured, but that does not generalise to plain headless runs. Relay conversations resume a `.jsonl` and are written (123 of 305 conversations present earlier, section 3).

Not verified: interactive TUI, resume or branch capture, compaction, a second worktree, queue/ack and indexing provenance, the Mac.

## 14. Follow-up fixes merged in the fork, and what the installed binary shows (2026-11-20 04:37)

The three Relay follow-ups landed in `zachbornheimer/oh-my-pi` branch `feat/archive-memory-backend` (head `c44cd91`, 2026-11-19): ZYS-10120 non-destructive, atomic supersession (#92, #93); ZYS-10145 no-transcript retention outcome and a one-shot drain (#94, #96, #97); ZYS-10146 fall back to local session files when `SESSIONS_DB_URL` is unreachable (#95). ZYS-10143 landed in `dev-profile` (#225, #226; judge deadline 5000 ms).

| Check | Result |
|---|---|
| Real-Postgres supersession replay, section 10, re-run against fork head `c44cd91` | 4 tests, 22 expects, pass. Supersession, as-of history, scope isolation and idempotency still hold after #92-#97. |
| Fork's own `archive.test.ts` at `c44cd91` | Could not run here: `bun test` fails to load the native module (`packages/natives/native/index.js`), a build prerequisite of this sandbox, not a test result. |
| Outage probe on the **installed** binary (omp 19.0.0 build 20261119211213-4530cba) | Unchanged: exit 1, `PostgresError ERR_POSTGRES_CONNECTION_REFUSED`, no answer. |

**Inference, not verified:** the installed build probably predates the merged fork fixes. Its version string is a build stamp dated 2026-11-19 21:12 (hash `4530cba`, which is not an object in the fork checkout I have), while the fork head `c44cd91` is dated 2026-11-19 23:19, and the outage probe still fails as before. I did not confirm which commits the binary contains, and I could not build the fork to test the fixes.

Still not verified: a pinned-build probe of ZYS-10145 and ZYS-10146, Mac, interactive, resume, compaction, a second worktree, System One latency (no key), original benchmark fixtures.

## 15. ZYS-10146 fix verified at unit level; ZYS-10145 not run (2026-11-20 04:47)

The ZYS-10146 fix is not on the memory branch. It merged into `oh-my-pi` `chore/fork-upstream-compat-4530cba` as #95 `d1763e2` and #98 `ff636221`, whose parent is upstream `4530cba`, the same hash as the installed build `20261119211213-4530cba`. So the installed binary's base is the right line, but I did not establish whether the binary includes `d1763e2` or `ff636221`.

`docs/design/agent-memory-session-store-fallback-zys-10118.test.ts` imports the real `session-storage-env.ts` at `ff636221` with its native-dependent imports mocked, and passes (2 tests, 5 expects):

| Case | Result |
|---|---|
| `SESSIONS_DB_URL` pointing at a closed port | `resolveSessionStorage` returns `FileSessionStorage` twice, with exactly one `Session store unreachable` stderr notice |
| `SESSIONS_DB_URL` unset | `FileSessionStorage`, no notice |

This shows the fixed logic degrades instead of throwing. It does **not** show the installed binary does: the same `omp -p` outage probe at 04:37 still exited 1 with `PostgresError`. Either the binary predates the fix or a second code path reads the URL outside `resolveSessionStorage`; I could not tell which.

ZYS-10145 (no-transcript outcome #94/#96, drain #97) lives in `feat/archive-memory-backend`. Its own tests need the native module, which needs a Rust toolchain absent here, so they were not run. Only the capture probe on a rebuilt binary can close it.

Still open: rebuild the fork into the pinned binary and repeat the section 13 probes; Mac, interactive, resume, compaction; System One latency; original fixtures.

Narrowing the outage abort (read from source at `ff636221`, not run): `SESSIONS_DB_URL` has two readers. `session-storage-env.ts` now degrades (verified above). The archive memory backend's `openArchiveClient` is lazy and `backend.ts` wraps its queries in `catch`, so it does not throw on an unreachable store either. Neither reader explains the installed binary's exit 1, which points to a build without the fix; I could not confirm that without running the fork.

## 16. Fork tests run here without Rust; the installed binary lacks the fixes (2026-11-20 06:20)

The Rust toolchain is not needed to run the fork's TypeScript tests. The installed `omp` build extracts its native addon to `~/.omp/natives/19.0.0/`; copying that one file to `packages/natives/native/` in a fork checkout (after `bun install --frozen-lockfile --ignore-scripts`) lets `bun test` load it. The loader warns the addon is 19.0.0 and the checkout 18.18.9, so results are indicative of the TypeScript logic only.

| Check | Result |
|---|---|
| `oh-my-pi` `feat/archive-memory-backend` @ `c44cd91`, `test/memory-backend/archive.test.ts` | 60 pass, 0 fail, 234 expects. Includes the ZYS-10145 cases (reports `skipped: no-transcript`, drain waits for an in-flight write, status names a session with no transcript) and the ZYS-10120 supersession case. |
| `oh-my-pi` `chore/fork-upstream-compat-4530cba` @ `ff63622`, `test/session/session-storage-env.test.ts` | 6 pass, 0 fail, 14 expects. ZYS-10146: an unreachable store prints `Session store unreachable (...); memory and sessions fall back to local files for this run.` and the run continues. |
| Installed binary `build-20261119211213-4530cba-4785fc9`, string search | `Session store unreachable`, `no transcript file`, `skipped retention`, `drain in-flight`, `memory_fact_history`: 0 hits. `superseded_by`: 94 hits. |
| Installed binary, outage probe (`SESSIONS_DB_URL` closed port) | exit 1, `PostgresError ERR_POSTGRES_CONNECTION_REFUSED`, no answer (06:16). |

So the fixes are correct in source and pass their own tests, and the installed binary does not contain them: the strings are absent and the probe still fails. The remaining gap is a rebuild of the pinned binary from the merged fork, which needs the Rust toolchain.

### Where captured sessions actually live

With `SESSIONS_DB_URL` set, OMP stores session transcripts in Neon (`public.omp_session_files`, `omp_session_files_entries`), not under `~/.omp/agent/sessions`. That is why `omp -p --session-dir <dir>` leaves the directory empty. My earlier section 13 claim that plain `omp -p` runs "write no transcript" was wrong: a probe session `-Developer-Personal-dev-profile/2026-11-20T06-14-10-334Z_*` has 12 entries in `omp_session_files_entries` (title, session, model_change, message user and assistant, `session_exit`). It has 0 rows in `memory_chunks`, so the real gap is the retention step, not transcript persistence. The Relay conversation transcript has 11 user turns (01:12 to 05:57) and 13 chunks in `memory_chunks`, all from the first prompt and the first four assistant replies up to 01:39:22; nothing after 01:39 was retained.

Resume check: `omp -c --session-dir <dir> -p` recalled a token set in the previous `omp -p` run, so resume restores the stored transcript.

Still not verified: Mac, interactive TUI, compaction, a rebuilt binary, System One latency reproduced here.
