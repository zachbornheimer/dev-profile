---
name: in-browser-database
description: >
  Design and build apps that hold data in an in-browser database (IndexedDB,
  SQLite-WASM/OPFS, Turso WASM) and sync it with a server — offline-first /
  local-first architecture. Use when starting any app, dashboard, editor, or
  feature that mentions an in-browser database, client-side storage, IndexedDB,
  OPFS, SQLite in the browser, offline support, instant Linear-like updates,
  realtime sync engines, multi-client collaboration, or choosing between
  Electric SQL, PowerSync, Zero, TanStack DB, Jazz, LiveStore, Dexie Cloud,
  Triplit, or Instant. Load BEFORE writing any client-side persistence code —
  even a "simple" localStorage cache — if it could ever need sync, offline, or
  multi-device use.
---

# In-browser databases and local-first sync

When an app keeps its own database in the browser, the interaction path loses
network latency: writes land in the local database instantly and sync happens
in the background. Linear is the reference product. Its engine is worth
copying conceptually even when you don't copy the code.

## Rule 1: do not hand-roll a sync engine as a first move

The hard part is never the storage. It is: offline/online transitions,
conflict resolution, partial sync (you cannot download the whole database),
schema migration of cached data, and permissions enforced across a
distributed system. Even the basic version of Linear's engine is months of
engineering. Reach for an off-the-shelf sync layer first; hand-roll only when
one demonstrably cannot do what the app needs.

## Pick the sync layer

| Layer                     | Model                                             | Use when                                                      | Watch out                                                                                                                                   |
| ------------------------- | ------------------------------------------------- | ------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| Electric SQL              | Reactive "Shapes" synced from Postgres            | You already have Postgres                                     | Mutations not included; pair with TanStack DB or LiveStore                                                                                  |
| Zero                      | Postgres-backed queries + mutations               | Electric-like sync with writes included                       | Younger ecosystem                                                                                                                           |
| PowerSync                 | Postgres/MySQL/Mongo sync                         | Enterprise requirements                                       | Heavier; commercial                                                                                                                         |
| TanStack DB               | Client reactive layer over a sync backend         | Decouple client UX from sync choice                           | A layer, not a backend                                                                                                                      |
| LiveStore                 | Event-sourced reactive store over Electric (etc.) | Event-sourcing + local-first together                         | Imposes its own schema requirements on the Postgres DB                                                                                      |
| Jazz                      | Encrypted CoValues, group permissions             | Rapid prototyping; privacy-first; no server business logic    | Server is BLIND (E2E encryption); history is never deleted → GDPR + storage growth; passkey auth needs HTTPS everywhere (painful local dev) |
| Dexie Cloud               | Sync for Dexie.js apps                            | Already on Dexie                                              | Dexie-scoped                                                                                                                                |
| Triplit / Instant         | Full-stack local-first, DX-focused                | Small greenfield apps                                         | Smaller ecosystems                                                                                                                          |
| Turso (Limbo) WASM + OPFS | Embedded SQLite in browser, with sync             | SQL in the browser; load the `turso-db` skill for SDK details | Sync story newer than the engine                                                                                                            |
| Hand-rolled LSE-style     | Own transactions + delta log                      | Nothing above fits (rare)                                     | Read `references/sync-engine-patterns.md` first                                                                                             |

Decision heuristics:

- Already have Postgres → Electric or Zero; add TanStack DB for client reactivity.
- Server must read all data (moderation, billing, analytics) → NOT Jazz-style E2E encryption.
- GDPR deletion required → avoid append-only designs, or design retention before launch.
- Server-side validation frequently rejects writes (billing, quotas) → optimistic updates get corrected constantly. Keep those fields server-authoritative.

## When local-first is the wrong call

Good fit: creative tools, collaborative editors, dev tools, offline-capable
mobile, personal productivity.
Bad fit: heavy server-side business logic, strict audit trails, large-scale
analytics, deep legacy integrations, and any surface where the server
regularly rejects requests. Membership/billing/checkout surfaces are
server-authoritative, always.

## If you hand-roll: the proven shape (Linear + Figma)

Read `references/sync-engine-patterns.md` before writing code. The
non-negotiables:

1. Server owns a total order. Every committed transaction gets a monotonic
   sync id; the client's `lastSyncId` is its local database version. This is
   OT-flavored (central server), not CRDT — no vector clocks, no merge
   metadata, because the server is the authority.
2. Last-writer-wins per property, not per object. Two clients editing
   different properties of the same object never conflict.
3. Client-generated IDs, prefixed with a client id. Creation must work
   offline; the server cannot assign IDs.
4. Optimistic application + anti-flicker. Apply writes locally immediately.
   When a server delta arrives for a property with an unacknowledged local
   change, discard the delta — your unacked change is the best prediction of
   the eventual value.
5. Durable outbound queue. Persist outbound transactions in a local table
   before sending; delete only on server ack; resend on reconnect. A closed
   tab must never lose a write.
6. Delta sync protocol. Bootstrap returns full model dumps plus
   `_metadata_={lastSyncId, subscribedSyncGroups, databaseVersion}`; a delta
   endpoint replays sync actions from `lastSyncId` forward; a WebSocket pushes
   deltas live. Mutations request only `lastSyncId` back.
7. Schema hash for cache migration. Hash model+property metadata; on mismatch
   with the stored hash, migrate or drop and re-bootstrap.
8. Partial sync via sync groups. Subscribe by user/team/role ids; permissions
   are which deltas can reach you. Never download the whole database.
9. Ship-behind-flag (`local` load strategy). Persist a new model client-side
   only until the server catches up, then flip its load strategy. Features can
   ship before backend support exists.
10. Undo that composes with collaboration. Undo modifies redo history at the
    time of undo — "undo a lot, copy, redo to present" must not change the
    document. Deletes keep no server-side property tombstones; the deleting
    client's undo buffer restores them, which keeps long-lived documents
    small.
11. Trees: store the parent link plus fractional-index position as one
    atomic property on the child. The server rejects updates that would
    create cycles; a client temporarily hides objects in a would-be cycle
    until the server resolves it.

## Verification bar for any local-first build

Before calling a sync surface done: run two clients side by side and watch one
write land in the other; kill the network mid-write, write more, reconnect, and
confirm zero loss and correct ordering; delete the local database and confirm
bootstrap rebuilds it; change the schema and confirm the cache migrates or
re-bootstraps instead of crashing.

## Sources (read order)

1. Reverse engineering Linear's sync engine (CTO-endorsed, mid-2025):
   <https://github.com/backupManager/reverse-linear-sync-engine-dev>
   (README + SUMMARY.md)
2. Protocol-level DevTools breakdown (Dec 2022; shows the wire format):
   <https://marknotfound.com/posts/reverse-engineering-linears-sync-magic/>
3. Figma multiplayer (property LWW, trees, undo):
   <https://www.figma.com/blog/how-figmas-multiplayer-technology-works/>
4. Local-first ecosystem tour (Jazz tradeoffs, fit matrix):
   <https://bytemash.net/posts/i-went-down-the-linear-rabbit-hole/>

Staleness warning: Linear ships roughly every half hour; the 2025 writeup
watched the model count go from 76 to 80 while being written. Treat specifics
as directional. The patterns above are the durable part.
