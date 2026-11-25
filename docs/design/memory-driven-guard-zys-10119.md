# Memory-driven guard (ZYS-10119): design and opt-in pre-tool guard

Follows the ZYS-10118 baseline (`agent-memory-baseline-zys-10118.md`, section 2): recall runs once per session, and `onPreToolUse` / `onStop` had no memory logic, so nothing could interrupt a call that conflicts with an approved project decision after the first prompt.

Marks: **[M]** measured here, **[S]** read from source, **[I]** inference.

## Decision

An opt-in guard, `OMP_MEMORY_GUARD=on` (default off, like `OMP_SCOPE_GUARD`). Off means no recall, no model call, no behavior change [M: the existing `onTool`/`decidePreToolUse` tests still pass].

| Moment                            | Where                                                                            | What                                                                                                                                      |
| --------------------------------- | -------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| Before a mutating tool call       | `hooks/tool_use.ts` -> `memoryToolBlock`                                         | Recall decisions for the proposed call, keep this repository's current ones, ask one judge question, block once with the decision quoted. |
| Before a final answer is accepted | `onStop.ts` -> `createMemoryStopGate` (a `StopGate` in the main-agent gate list) | Same check on `last_assistant_message`; block once with "correct only the conflicting statement, do not repeat the rest".                 |

Files (extensions tree, tracked by `mise dot`, not in this repository): `hooks/memory_guard.ts` (policy), `prompts/memory_guard_ports.ts` (live recall + judge), `prompts/memory_conflict.yaml` (one `MemoryConflict` yes/no question), `hooks/memory_guard.test.ts` (replay).

## Rules

1. **Recall** reuses `retrieveMemoryShortlist` (the prompt hook's query), per call, 2 s deadline (`MEMORY_RECALL_DEADLINE_MS`; measured p50 63 ms / p95 213 ms). Only distilled `fact` rows are decisions; transcript chunks are never enforced.
2. **Project scope.** A row is enforced only if its `repository` equals the cwd's repo name, or the cwd is a worktree `<repo>-<slug>`. A row from another repository or with no repository is ignored.
3. **Stale memory.** The store has no `valid_to` / `superseded_by` column (ZYS-10120), so the guard ignores a body that says superseded / outdated / obsolete / no longer valid, and any fact older than 180 days. A decision with neither marker is treated as current. This is a heuristic, not supersession; real supersession needs ZYS-10120.
4. **No loop.** A per-session, per-ask ledger records each quoted decision id; the same decision is never quoted twice for one ask, and a new user ask resets it. An unchanged retry after the one block therefore runs. The Stop gate shares the ledger, so one decision costs at most one correction across tool call and final answer.
5. **Bounded Stop correction.** The Stop block reason tells the agent to correct only the conflicting statement and not repeat the answer, so the corrected stream carries no duplicate of the first answer. Subagent stops are not checked (the gate is registered by `onStop.ts` only).
6. **Fail open, but a deadline is never silent (ZYS-10143).** Guard off, no session id, recall or judge error, or a judge score below 0.8 lets the call or stop through, and is logged as `memory_skip`. The judge has `MEMORY_JUDGE_DEADLINE_MS` = 5000 ms, set from a measurement: `bench-memory-guard/latency.ts` posts the one `MemoryConflict` question for the 18 labeled cases to System One through the fleet gateway (3 rounds, n=54, 0 failures, 2026-11-20): p50 136-138 ms, p90 158-167 ms, p95 177-179 ms, max 208-277 ms over two runs. The prompt hook's multi-question `judge_ms` reached 4692 ms on the same sandbox, so 5000 ms also covers that tail; recall is 2000 ms (p95 213 ms); the two stay under omp's 10 s handler limit. The earlier 2500 ms failed open only on the real-model replay, where the judge was a general `omp -p` model (7.5-9.6 s), not System One. A recall or judge that still misses its deadline logs `memory_skip: recall-deadline` / `judge-deadline` with `deadline_ms`, and on a tool call the agent receives an `additionalContext` notice that the call was NOT checked, so it is never mistaken for "no conflict"; the call still runs. At Stop the deadline is written to the `onStop` fire log only (a refusal there would loop). Measured through the gateway from this sandbox, not from the Mac; rerun `ROUNDS=3 bun latency.ts` after any model change.
7. **Cost.** No model call unless a current same-repo decision is recalled; one judge call otherwise. Reads and control tools are skipped through the scope guard's `scopeSkip`.

## Proof

`hooks/memory_guard.test.ts` replays one scripted turn (proposals, then streamed final answers) through the real `decidePreToolUse` and Stop gate with an in-memory recall store and a deterministic judge:

| Case                                         | Blocks               | Duplicate streamed answers |
| -------------------------------------------- | -------------------- | -------------------------- |
| conflict (`npm install`, decision: bun only) | 1                    | 0                          |
| no conflict (`bun install`)                  | 0                    | 0                          |
| outdated (superseded body, 2025 fact)        | 0 (judge not called) | 0                          |
| cross-repo (other repository, no repository) | 0 (judge not called) | 0                          |

Plus: retry after the block is not blocked again; a worktree cwd counts as the project; guard off / judge down passes; a conflicting final answer is refused once and the correction stands.

## Not proven

- The judge is a fake: real `MemoryConflict` precision/recall on System One is unmeasured, so the 0.8 threshold is a starting value, not a result. The scope guard's own replay (18/77 caught, 63/300 false refusals) is the cautionary precedent; run an offline replay before enabling this by default.
- Live recall latency per tool call was not measured; the prompt hook's measured `memory_ms` was 115-154 ms [M, ZYS-10118].
- No Mac observation (Tailscale refused SSH from this sandbox, exit 255).
- The `fact` row's `repository` is whatever the writer stored; rows written with a different repo spelling are ignored (fail safe, possible misses).
