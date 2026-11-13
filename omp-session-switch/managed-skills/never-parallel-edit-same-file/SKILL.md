---
name: never-parallel-edit-same-file
description: Use before batching edit_replace or edit tool calls; two edits to the same file in one parallel block clobber each other (last writer wins on a stale snapshot)
---

# Never parallel-edit the same file

Batching two `edit_replace` (or `edit`) calls that target the **same file** in one parallel tool block silently drops one edit. Each call appears to succeed ("replaced 1 occurrence") because each applied against the snapshot it read, but the writes are read-modify-write: the second write lands without the first edit, or vice versa.

Observed three times in one session (omp-01a1bc5c, 2026-11-09): interface edits survived while the body edit in the same batch vanished; the failure only surfaced when tests ran the old code path. Symptom: tests fail on behavior you already "fixed", and the diff shows one of your edits missing.

Rules:
- Same-file edits go one call per turn (or one `edit_patch` carrying all hunks for that file).
- Parallel `edit_replace` across *different* files is safe.
- After any batched edit round that touched the same file twice, re-read the file before trusting either edit.

Short-term bridge until `optimize_tooling` / `relay` hardens the edit tools (a write-contention guard or stale-snapshot rejection); the durable fix is in the tools, not this skill.
