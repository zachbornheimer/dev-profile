# Self-improvement bead contract

The harvester produces evidence. The Mayor or reviewer turns only surviving
clusters into open beads.

## Required title

`[self-improve] Add|Refine <role|formula|skill|routing|guard>: <short outcome>`

## Required body

```markdown
## Repeated outcome

## Evidence
- session: <id>, date: <date>, repo: <repo>
- session: <id>, date: <date>, repo: <repo>
- session: <id>, date: <date>, repo: <repo>

## Current gap

## Proposed durable change

## Allowed paths

## Acceptance
- [ ] ...

## Verification observation

## Rejection test

<!-- gc.self_improve.status=proposed -->
<!-- gc.self_improve.evidence_count=3 -->
```

The bead remains open until an implementation worker, an independent reviewer,
and a fresh-process verification observation agree that the capability is real.
One-off or already-covered candidates are recorded as rejected evidence rather
than turned into work.
