---
name: omp-session-hibernation-observability
description: "Use when checking whether omp session hibernation is working, what it released, or why it did not hibernate; covers the JSONL event log, /hibernate commands, the drain primitives, and the RSS measurement caveats"
---

# omp session hibernation observability

The `session-hibernation` extension (`~/.omp/agent/extensions/session-hibernation/`) logs every controller decision to `~/.omp/agent/logs/session-hibernation.jsonl` (one JSON object per line, stamped with `pid` + session id, rotates to `.1` past 5 MB). "Is hibernation working" is a file read, not a guess.

## How to check

- Live: `tail -f ~/.omp/agent/logs/session-hibernation.jsonl`
- In a tab: `/hibernate` (stats + last before/after), `/hibernate now` (hibernate immediately), `/hibernate log [N]` (last N events)
- After editing the extension, sessions pick it up via `/reload-plugins`; a `loaded` record per process confirms registration.

## Event meanings

- `loaded`: extension registered (pid, execPath, graces, current rss/heap).
- `scheduled` (trigger=turn_stop|tool_call, delayMs): a hibernate timer armed.
- `cancelled` (cause=entry | tool_start | tool_finished_within_grace): why it did NOT hibernate. `tool_finished_within_grace` is normal for commands under 250ms.
- `skipped`: hibernate asked while already hibernated.
- `hibernate`: rss/heap/fd before->after, `reclaimedMb`, `dehydrateMs`, `gcMs`, plus per-`dehydrate_step` records.
- `wake`: `hibernatedForMs`, `rehydrateMs`, held rss/heap/fd.

## Drain semantics (the step that fails silently)

`drain_storage` result values tell the truth:
- `flush+ensureOnDisk`: correct — `SessionManager.flush()` drains queued writes plus the storage's fire-and-forget publishes, then `ensureOnDisk()`.
- `ensureOnDisk` alone: partial — returns early when the file is current; does not drain the queue.
- `no_flush_available`: the build predates `ReadonlySessionManager.flush` exposure (landed on fork `assembled`@`38303d1a71e8`; needs an omp build from that commit or later).
- `no_session_manager_on_context`: handler context had no sessionManager.

`flush` is exposed to extensions via `ReadonlySessionManager` and to cross-thread tools via `WireSessionView`/`ToolContextSessionView` (`packages/coding-agent/src/session/session-manager.ts`, `src/thread/services/tool-context.ts`).

`close_pools` result values: `closed` (zab-ai-tools `closeMemoryConnections` ran — export added to `catalog_ports.ts`), `zab_ai_tools_has_no_closeMemoryConnections_export` (old build; `/reload-plugins`), `zab_ai_tools_not_importable` (zab absent — fine).

## RSS caveats on macOS

`Bun.shrink()` often does not return pages: `reclaimedMb` can be negative (-10 to -12 MB noise observed) and `rssAfterMb` may exceed `rssBeforeMb` right after GC. The honest number is RSS at the next `wake` event. Judge hibernation by fd deltas and wake-time RSS, not by `reclaimedMb` alone.
