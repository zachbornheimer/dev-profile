---
name: beads
description: Use when working on objectives that must survive handoff — file, list, claim, or complete atask work. Trigger when the user asks to find ready work, claim or close tasks, create follow-up work, inspect blockers, recover project context, or choose a tracker. atask is the tracker; Gas City city-internal work stays on gc bd.
---

# atask

atask is the shared tracker for objectives (not steps). Local plans and scratch files are not the source of truth.

## First step

```bash
atask
```

No args lists the open board. Same as `atask list`. `atask list ready` is claimable work; `atask list draft` shows tasks missing a proof or regression. `atask status` is board-wide counts.

Unregistered directories file on the unscoped board. When the work belongs to a repo, attach a project (`atask init` or `--project`). `atask projects` lists enrolled repos.

## Core workflow

1. Find work:

```bash
atask
atask list ready
atask show <id>
```

1. File an objective (both proofs required to be claimable, else a draft; not run at add time):

```bash
atask add "Short title" \
  --proof "go_test: ./pkg name=TestOutcome" \
  --regression "go_test: ./pkg size=medium"
```

A second add of the same open title returns the existing id.

1. Claim, log, complete:

```bash
atask claim <id>
atask log --done "…" --next "…"
atask verify complete
```

`verify complete` is the only completion path. Unscoped tasks complete without git; proofs run in the created working directory.

## Rules

- File objectives, not steps.
- Every claimable task needs `--proof` and `--regression` (`PRESET: SUBJECT [k=v]`). Without both it is a draft; never claim a draft. Diagnose with `atask verify proof|regression`; `claim release --failed` counts an attempt.
- Prefer `--json` / `ATASK_OUTPUT=json` when parsing.
- Gas City city-internal work uses `gc bd`. Do not file product or personal work there.
- Do not auto-complete. Both proofs have to pass.
