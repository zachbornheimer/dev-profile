---
name: omp-hibernation-log-debugging
description: "Use when verifying or debugging omp session hibernation (SessionHibernator extension): where the event log lives, what each record means, and how to prove a hibernation actually released memory and connections."
---

# omp session hibernation log

The `session-hibernation` extension (`~/.omp/agent/extensions/session-hibernation/`) logs every controller decision as one JSON line to `~/.omp/agent/logs/session-hibernation.jsonl` (rotates to `.1` past 5 MB).

## Read it

- Live: `tail -f ~/.omp/agent/logs/session-hibernation.jsonl`
- In a session: `/hibernate log [N]` (last N records, formatted), `/hibernate` (stats + last before/after), `/hibernate now` (hibernate immediately).

## Records and what they prove

- `loaded` — extension registered; includes grace settings and a memory sample. No `loaded` line after `/reload-plugins` means the extension is not loading at all.
- `scheduled` — a hibernate timer armed (`trigger`: `turn_stop` with `delayMs`, or `tool_call` with tool name, `immediate`, `delayMs`).
- `cancelled` — the timer was disarmed before firing; `cause` says why (`entry`, `tool_start`, `tool_finished_within_grace`). Frequent `cancelled` events with no `hibernate` following = sessions never actually idle long enough.
- `skipped` — hibernate asked for while already hibernated/disposed.
- `dehydrate_step` — one per release: `drain_storage` (reports `no_drain_available` when the session manager exposes no `storage.drain`) and `close_pools` (names the closer used or why none ran; failures carry `error`). These expose a no-op dehydration.
- `hibernate` — the outcome: `rssBeforeMb`/`rssAfterMb`, `reclaimedMb`, heap before/after, `fdsBefore`/`fdsAfter`, `dehydrateMs`, `gcMs`, `dehydrateError`/`gcError`. This is the record that answers "did it work".
- `wake` — `hibernatedForMs`, `rehydrateMs`, and what the process held while asleep (rss/heap/fd).

Every record is stamped `pid` + `session` (session id), so multiple tabs are distinguishable in one file.

## Verification procedure

1. `/reload-plugins`, then confirm a `loaded` record exists (else the extension build failed).
2. `/hibernate now`, then read the `hibernate` record: reclaimed MB and fds delta. RSS must drop between `rssBeforeMb` and `rssAfterMb`; fds should drop when Postgres pools close.
3. If `reclaimedMb` is ~0: check `dehydrate_step` records — `no_drain_available` means no storage queue drained; `close_pools` result `zab_ai_tools_has_no_closeMemoryConnections_export` means the pool close is a no-op.
4. If no records at all appear after idle: look for `cancelled` (something keeps waking the session) or a missing `loaded` (extension not loaded). `session.hotReloadBinary: true` + herdr/tmux gates in `~/.omp/agent/config.yml:210` only govern binary reload, not hibernation.

## Gotchas

- macOS RSS lags decommit: an immediately-following `wake` record's `rssMb` can read lower than the `hibernate` record's `rssAfterMb`. Trust the trend, not one sample.
- `fds` counts entries of `/dev/fd` (one is the probe itself); only the delta matters.
- The log write failing never affects hibernation; `/hibernate` stats show `log: <path> (N written, M failed: <error>)`.

Action boundary: this skill is the reading/debugging procedure. The state machine itself lives in `~/.omp/agent/extensions/session-hibernation/` (`hibernator.ts`, `index.ts`, `event-log.ts`, tests in `hibernation.test.ts` / `event-log.test.ts`); spec: `~/.local/share/specs/omp-hibernation-and-sql-session-storage/spec.md` Part 3. If hibernation verification becomes a repeated workflow, promote this to a tool that reads the log and renders a verdict.
