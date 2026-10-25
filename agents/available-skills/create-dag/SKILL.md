---
name: create-dag
description: Build a dependency DAG of work items (tickets, issues, tasks) rendered in tree notation — parallel-by-default, nesting only for proven hard dependencies. Use when asked to "create a DAG", sequence a batch of tickets, or decide what can run in parallel.
---

# create-dag — dependency graph of work items in tree notation

Produce a DAG that tells an orchestrator what can be dispatched **right now in
parallel** and what must wait. The graph is the schedule; a wrong edge either
serializes work needlessly or ships a fix built on sand.

## Core assumptions (binding)

1. **Parallel is the null hypothesis.** Every item starts as a root. You must
   _earn_ an edge with evidence; "feels related", "same file area", or "same
   theme" is NOT an edge.
2. **An edge means a hard dependency:** the child cannot be _started or
   verified_ until the parent lands. Two valid reasons only:
   - **Build-on:** the child's fix modifies state the parent's fix creates or
     reshapes (e.g. child consumes an artifact the parent's change regenerates).
   - **Masked-verification:** the child's done-condition cannot be observed
     GREEN until the parent is fixed (parent's failure hides or falsifies the
     child's signal).
3. **Shared root cause is nesting, not duplication.** If two items are the same
   underlying defect, pick the item that names the root as parent and nest the
   symptom item under it.
4. **Multi-parent items:** the tree can't express two parents. Place the item
   under its _primary_ (longest-pole) blocker and annotate the rest inline:
   `MI-105 (also after: MI-050, MI-054)`.
5. **Unknowns stay parallel.** If you cannot articulate the edge's reason in
   one sentence of evidence, the item stays a root. Never invent ordering to
   look organized.

## Procedure

1. **Inventory.** List every item with a one-line summary and its current
   status (open / in-flight / needs-diagnosis). Do not drop items; if an item
   is out of scope, list it under an explicit `excluded:` note with the reason.
2. **Evidence pass.** For each candidate edge, write the one-sentence
   justification (build-on or masked-verification, and why). Discard any edge
   you can't justify from the provided evidence or the codebase.
3. **Render the tree** (format below).
4. **Edge ledger.** After the tree, list every edge with its one-sentence
   justification: `MI-A → MI-B: <reason>`. Every nesting in the tree MUST have
   a ledger line; a ledger line without a nesting is a bug.

## Output format

Use `tree`-style notation. Roots are all mutually parallel; every level of
children under one parent is also mutually parallel.

```text
├── MI-XXX — short label
├── MI-YYY — short label
├── MI-ZZZ — short label
│   ├── MI-ZAA — short label
│   ├── MI-ZAB — short label
│   │   └── MI-ZBB — short label
│   └── MI-ZAC — short label (also after: MI-YYY)
└── MI-WWW — short label
```

Rules:

- Branch glyphs: `├──` for every sibling except the last, `└──` for the last;
  continuation columns use `│` while an ancestor has more siblings, `    `
  (four spaces) otherwise.
- One node per line: `MI-NNN — label` (label states the defect, not the fix).
  Append annotations in parentheses: secondary parents (`also after: …`),
  status flags (`needs-diagnosis`, `in-flight`, `owner-gated`).
- Keep every line ≤ 80 characters (codepoints, including glyphs and indent) —
  markdownlint MD013 applies inside the fence in repos that gate on it.
- Sort siblings numerically by ticket id.
- Each item appears exactly once in the tree.
- Wrap the tree in a fenced code block so the glyphs survive rendering.

## Deliverable

A single markdown document containing, in order: a one-paragraph read of the
graph (how wide the first wave is, what the longest chain is), the tree, the
edge ledger, and the excluded-items note (if any). Write it to the path the
requester names; otherwise return it inline.
