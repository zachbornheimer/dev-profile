# Sync engine patterns: detailed notes from Linear (LSE) and Figma

Condensed from the reverse-engineering study (2025), the DevTools breakdown
(2022), and Figma's multiplayer writeup (2019). Wire-level specifics are from
2022 — treat shapes as directional, not current.

## Linear Sync Engine (LSE) architecture

### Models

- Models are entities (`Issue`, `Team`, ...) held in an Object Pool keyed by
  UUID, loaded from IndexedDB or the server.
- `ModelRegistry` is a static dictionary of metadata: model name →
  constructor, property metadata, reference metadata.
- TypeScript decorators register metadata at class-definition time:
  `@ClientModel("Issue")`, `Property`, `Reference`, `BackReference`, etc.
- Model metadata fields:
  - `loadStrategy`: `instant` (loaded at bootstrap, default), `lazy`
    (all-at-once when first needed), `partial` (subset on demand),
    `explicitlyRequested` (only when asked), `local` (client-side only,
    until server support lands — the ship-behind-flag).
  - `partialLoadMode`: `full` | `regular` | `lowPriority`.
  - `usedForPartialIndexes`.
- Property metadata fields: `type`, `lazy`, `serializer`, `indexed`,
  `nullable`.
- Property types:
  - `property` (owned by the model), `ephemeralProperty` (not persisted).
  - `reference` (stores target's id; lazy-loadable), `referenceModel`
    (getter/setter built over a reference), `referenceCollection` (array of
    ids).
  - `backReference` (inverse of a reference; owned by the TARGET — when the
    referenced model is deleted, the backReference is deleted too).
  - `referenceArray` (many-to-many).
- Observability via MobX: models are not observable at construction; a
  `hydrate` call populates values lazily on first access and observability is
  switched on at the right moment.
- `__schemaHash`: hash over all model + property metadata, stored client-side;
  a mismatch against the local database means migrate or re-bootstrap.

### Bootstrapping flow

1. `StoreManager` creates a `PartialStore` or `FullStore` per model, plus a
   `SyncActionStore`.
2. `Database` connects to IndexedDB; creates databases/tables; performs
   migrations.
3. Full vs incremental bootstrap is chosen.
4. Models are fetched from the server and written to IndexedDB.
5. Instant-strategy models are hydrated into memory; observability on.
6. A WebSocket is opened for delta packets.
- One IndexedDB database per logged-in workspace. Its metadata holds
  `lastSyncId`, `firstSyncId` (the `lastSyncId` captured at full bootstrap —
  the start point for incremental sync), `subscribedSyncGroups`,
  `databaseVersion`.

### Wire format (observed Dec 2022)

- `GET /sync/bootstrap?type=full&onlyModels=ApiKey,...` responds `text/plain`,
  one `ModelName={json}` per line, ending with
  `_metadata_={"method":"postgres","lastSyncId":...,"subscribedSyncGroups":[...],"databaseVersion":...}`.
- A second bootstrap with `type=partial` loads high-volume, low-priority
  models (`Comment`, `IssueHistory`).
- Mutations are GraphQL and typically request ONLY `lastSyncId` in the
  response. The authoritative result arrives later as a delta packet, so
  server side effects (history generation, etc.) are reflected, not the
  client's guess.
- WebSocket push: `{"cmd":"sync","sync":[<SyncAction>...],"lastSyncId":...}`.
- SyncAction: `{id, modelName, modelId, action ∈ I/U/D/A, data}`.
- `GET /sync/delta?lastSyncId=&toSyncId=` replays the SyncActions the client
  missed; the client detects gaps by comparing ids.

### Transactions

- A property assignment records `(property, previous value)` and updates the
  in-memory model immediately. `model.save()` creates an `UpdateTransaction`.
- The transaction enters a request queue AND is persisted to the
  `__transactions` table in IndexedDB before any network send — a closed tab
  or dropped connection must not lose the write.
- A timer batches queued transactions to the server; on success the batch row
  is deleted.
- The transaction does not resolve until a delta packet containing its
  `lastSyncId` arrives — the delta may differ from what was sent because of
  server side effects.
- Conflict resolution is last-writer-wins, per property.
- Undo/redo/revert are transaction-level; a transaction is designed to be
  reversible on the client so a server rejection can be rolled back cleanly.

### Delta packet handling order

1. Apply sync-group membership changes (user added/removed from groups).
2. Load dependencies the actions need.
3. Write new sync-group data and its dependents into the local database.
4. Resolve all sync actions against the local database.
5. Resolve all sync actions against in-memory models.
6. Update `lastSyncId` (and `firstSyncId` if sync groups changed); release
   transactions waiting on that id.

### lastSyncId semantics

A global monotonic counter, incremented once per committed transaction —
effectively the database's version number. Ordering comes from one central
server, which makes this OT-flavored rather than CRDT: no peer ordering, no
merge metadata, no tombstones for ordering purposes.

### Sync groups

`subscribedSyncGroups` holds UUIDs of the user id, team ids, and role ids.
All workspaces share the `lastSyncId` counter; access control is simply which
deltas can reach a given client. This is how partial sync and permissions are
the same mechanism.

## Figma's multiplayer rules (differences from Linear)

- Document data lives outside Postgres in a dedicated multiplayer system;
  comments/users/teams sync through Postgres with a separate mechanism.
  Two sync systems, different tradeoffs — do not force one to serve both.
- Property-level last-writer-wins with no timestamps: the server defines the
  order, so wall-clock time is never a tiebreaker.
- Anti-flicker: discard incoming server deltas that conflict with an
  unacknowledged local property write. Your unacked write is the best
  prediction of the eventual value.
- Object creation and removal are explicit protocol actions. The server keeps
  NO property data for deleted objects — restore data lives only in the
  deleting client's undo buffer. Keeps long-lived documents from growing
  forever.
- Object IDs embed a client id, so offline creation cannot collide.
- Trees: the parent link and the fractional-indexing position are stored as
  ONE atomic property on the child (reparent + reorder must move together).
  The server rejects parent updates that would form a cycle. A client that
  holds an unacked reparent conflicting with an incoming one temporarily
  removes both objects from the tree until the server's rejection arrives.
- Undo: an undo modifies redo history at the time of the undo, and vice
  versa. Invariant: undo many steps, copy something, redo back to the
  present — the document is unchanged.
- Reconnect is dumb and that is a feature: re-download the full document,
  reapply offline edits, open a new WebSocket. All multiplayer complexity
  lives in the connected state.

## Jazz tradeoffs (from hands-on use, 2025)

- End-to-end encryption means the server cannot read data not explicitly
  shared with a server account via a Group. Anything the backend must see —
  moderation, billing, search — has to be planned up front.
- Event sourcing means "delete" only removes references. GDPR erasure and
  storage growth are design problems from day one.
- Passkey-first auth requires HTTPS off localhost; local-dev LAN testing
  cascades into mkcert → Clerk → key transfer → secure WebSocket proxying.
  Budget for it or pick a different auth path.
