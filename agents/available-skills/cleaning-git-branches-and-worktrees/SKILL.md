---
name: cleaning-git-branches-and-worktrees
description: Audit and safely prune many local Git branches and worktrees while preserving uncommitted or unmerged work. Use for repository-wide branch/worktree cleanup, reconciliation, or determining what is safe to remove. Do not use for one known branch, merge/rebase conflicts, remote-branch administration, repository-size cleanup, or general code cleanup.
---

# Clean Git Branches and Worktrees

Reconcile local branches and worktrees without losing recoverable work. Inventory, snapshot, and prune with `wt`.

## Gotchas

- `unsure` means keep. Unknown evidence is not clean evidence.
- Always pass `--foreground` on mutating `wt` commands (background is the default).
- Do not use `wt merge` as cleanup.
- `--force` only after `preserve-local-git` covered that dirty tree.
- Detached rows have `branch: null`; remove them by path.
- `wt step prune` skips locked, dirty, and the main worktree. Default `--min-age 1d`.
- Never `zq prune --apply` during audit.
- Keep `scripts/inventory.py`, `residual.py`, and `backup.py`. Extra evidence, and the fallback when `wt` is missing.

## Mode

Infer the narrowest mode that satisfies the request:

- **Audit:** inspect and classify only.
- **Cleanup:** audit first, then remove verified settled state when the user explicitly asked to clean, prune, remove, or reconcile it.
- **Ambiguous:** audit only.

Explicit invocation selects this workflow, not broader mutation authority.

## Safety boundary

`unsure` means keep.

Never remove:

- the default branch;
- a branch with a verified open PR;
- unique work that has not been preserved;
- uncommitted or untracked work that has not been preserved;
- a candidate whose current tip differs from the reviewed SHA.

If worktree status, PR state, branch identity, or another required safety check cannot be established, keep that candidate unresolved.

## Audit

### 1. Refresh

Resolve the repository, default branch, and reviewed base SHA.

```bash
git fetch --prune
```

If refresh fails, continue but mark remote-dependent conclusions unresolved.

### 2. Inventory

From the repo (or pass `-C <repo>`):

```bash
wt list --format=json
```

Schema 2 envelope `{schema,repo,collected,items}`:

- `items[].display.state`: empty, `_` (same commit as default), or `⊂` (content integrated)
- `items[].worktree.changes`: staged / modified / untracked
- Detached: `branch` is null; remove later by path

`_` and `⊂` are integrated prune candidates. Dirty changes stay unresolved until preserved. Detached stays unresolved until HEAD and local state are preserved or reconciled.

When PR lookup is needed (open vs merged vs landed), also run:

```bash
python scripts/inventory.py <repo> --out inventory.json
python scripts/residual.py inventory.json --out residual.json
```

If `wt` is missing, those scripts are the inventory.

Initial dispositions from `inventory.py`:

| Class       | Disposition                                        |
| ----------- | -------------------------------------------------- |
| `protected` | keep                                               |
| `open-pr`   | keep                                               |
| `landed`    | settled candidate                                  |
| `merged-pr` | settled candidate                                  |
| `duplicate` | settled candidate while its canonical copy remains |
| `orphan`    | review                                             |

If `inventory.json` reports `pr_lookup.status != "ok"`, PR-dependent cleanup is unresolved. Do not infer that a branch has no open PR.

Residual fields (`landed_ratio`, `hint`, conflict state, missing-line samples) prioritize investigation. They never authorize deletion.

### 3. Review only unresolved work

Review orphan branches that could plausibly be removed. Follow [references/triage-prompt.md](references/triage-prompt.md).

- `unique` → recover
- `superseded` → settled
- `obsolete` → settled
- `unsure` → unsure

Before relying on a model verdict for cleanup, verify its consequential evidence against the pinned base SHA.

### 4. Action set

Every candidate ends in exactly one set:

- **keep** — protected, open-PR, or active work
- **settled** — proven landed, duplicated safely, superseded, or obsolete
- **recover** — useful work still absent from the base
- **unsure** — insufficient or conflicting evidence

Audit mode stops here. Report counts plus every `recover` and `unsure` case.

## Cleanup

Cleanup may operate only on the settled set. Follow [references/cleanup.md](references/cleanup.md).

Leave `keep`, `recover`, and `unsure` untouched.

Pair with `preserve-local-git` only after origin holds unique tips.

## Verify

```bash
wt list --format=json
python scripts/inventory.py <repo> --out inventory-after.json
```

If `wt` is missing, inventory.py alone.

Confirm intended removals are gone; protected, open-PR, recover, and unsure remain; no SHA-changed candidate was removed; removed dirty state is recoverable; backup verifies when the fallback path ran. Stop further removal on discrepancy.

## Final report

Audit: branch/worktree counts, action-set counts, `recover` and `unsure` cases, proposed cleanup scope.

Cleanup: before/after counts, removed, kept or skipped, unresolved/recoverable work, backup location with restore command when used.

When removal lists are large, save the complete list in the cleanup output and summarize it in the response.
