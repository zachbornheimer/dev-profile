# Universal standards — cross-language gaps

Principles that don't belong to a single language but aren't in `gotchas.md`.
Gotchas-first; grow this from real failures.

## Review severity prefixes (mandatory on every comment)

Every review comment opens with a bracket prefix. No exceptions — prefixes let
the author triage without reading the full comment:

```
[nit]        Minor style preference; optional to address.
[suggestion] Consider this alternative; the author decides.
[question]   Need clarification before I can assess.
[blocking]   Must fix before merge.
```

Use one per comment, never stacked. If a comment is blocking, don't hedge it as
a suggestion. If it is genuinely optional, label it nit so the author doesn't
waste time debating it.

## TODO four-line format

Every TODO that lands in a commit must have all four lines — no exceptions, no
one-liners:

```
// TODO(owner): Description of what and WHY.
// Context: Why this shortcut was taken and why it is acceptable now.
// Tracking: Link to Linear ticket / GitHub issue.
// Deadline: When this must be fixed (quarter, release, or "before ship").
```

A TODO without owner + tracking + deadline is a bug waiting to be forgotten. The
format makes every TODO auditable: grep for `TODO` without a `Tracking:` line to
find strays.

## Trust the runtime

Any override of a runtime or stdlib default (concurrency limit, buffer size,
pool depth, timeout, retry count) needs a **cited measurement** in the code.
If no measurement exists, remove the override — do not document it with a
comment.

The rule is asymmetric: removing a unjustified override is safe (runtime handles
it). Keeping an unjustified override is tech debt that accumulates.

```go
// ❌ No evidence — remove it
const maxWorkers = 64

// ✅ Evidence cited
// Benchmark 2026-03-14 (bench_concurrency_test.go): 64 workers saturates
// the NFS volume at ~180 MB/s; 128 shows no throughput gain.
const maxWorkers = 64
```

See `go.md` for the Go-specific `runtimeinfo.DefaultWorkerCount()` pattern.

## Algorithmic complexity + data-structure quick tables

### Choose the right structure

| Need                               | Use                                                                       | Why                      |
| ---------------------------------- | ------------------------------------------------------------------------- | ------------------------ |
| Lookup / membership / dedup        | `map`                                                                     | O(1) average             |
| Ordered iteration over sorted data | sorted slice + `slices.BinarySearch`                                      | cache-friendly           |
| String construction in a loop      | `strings.Builder` (Go) / `StringBuilder` (Java/C#) / `''.join()` (Python) | avoids O(n²) allocations |
| Queue (FIFO, bounded)              | channel (Go) / `collections.deque` (Python)                               | idiomatic                |

### DB-scale bulk operations

| Pattern                                        | Problem                             | Fix                                      |
| ---------------------------------------------- | ----------------------------------- | ---------------------------------------- |
| `UPDATE … WHERE status = ?` (no LIMIT)         | Locks millions of rows atomically   | Add `LIMIT 1000` + loop                  |
| `DELETE FROM table` (no WHERE / LIMIT)         | Deletes all rows in one transaction | Batch delete with progress               |
| `SELECT COUNT(*)` on large table               | Full table scan per call            | Cached counter column or estimated count |
| `for id in ids: UPDATE … WHERE id = ?`         | O(n) round trips                    | `WHERE id IN (…)` or bulk UPDATE         |
| `INSERT … SELECT` without index on SELECT side | Full scan on every insert batch     | Add covering index first                 |

Bulk UPDATE / DELETE over large tables: always `LIMIT N` in a loop, commit
each batch. Never one giant transaction — it holds locks and fills WAL.
