# Verdicts

One verdict per open PR. Then cluster. Labels, drafts, and bot authors are
inputs, not the verdict.

## Verdict enum

<!-- markdownlint-disable MD013 -->

| Verdict             | When                                                                                                                                                                             | Action                                                                                                                                     |
| ------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| `merge_as_is`       | `baseRefName == defaultBranch` + `MERGEABLE` + `CLEAN` + branch current + intent still matches default + small focused diff                                                      | Lander on this PR; after merge, prove the explicit merge OID is on default                                                                 |
| `rebase_then_merge` | `baseRefName == defaultBranch` + mergeable but `BEHIND`, no conflicts, intent still matches, age < 14 days; more than one merge behind current default is `recreate`, not rebase | Worktree, rebase onto default, then lander; after merge, prove the explicit merge OID is on default                                        |
| `recreate`          | `CONFLICTING` / `DIRTY`, age ≥ 14 days and not `CLEAN`, draft-stale, `agent:pause` / `agent:blocked`, overlapping cluster, or labels contradict mergeability                     | New branch from **current default**. Port intent, tests, and the actual fix. New PR. Close original as superseded after the new one merges |
| `close`             | Duplicate of a landed change, empty/no-op, explicitly abandoned, or superseded (see below)                                                                                       | Comment rationale + surviving PR/OID or default SHA. Close. Human gate only if unique intent is discarded                                  |
| `hold`              | Owner-only human-gate item, or a research-tier item research could not decide                                                                                                    | Named reason. Do not dispatch a merger until research resolves it or the owner decides                                                     |

<!-- markdownlint-enable MD013 -->

Recreate is the default under uncertainty. The original branch is not owed a
merge.

## Superseded identification (mandatory)

Classify must **find and close** superseded PRs. Do not leave them OPEN as
leftovers, and do not recreate a PR whose intent is already gone.

A PR is superseded — verdict `close` — when any of these is true against
**current default** and the rest of the open cohort:

1. **Default already has the intent.** The proposed tree matches default, or
   default has moved to a different intentional state (lander step 0). Evidence:
   path-level diff vs current default, plus the surviving merge OID or default
   SHA.
2. **A surviving sibling carries the intent.** Same ticket, same files, or same
   claim as another open PR that will be the one recreated or merged. Close the
   weaker/older/draft duplicate now. Evidence: surviving PR number.
3. **A later merge already shipped it.** A merged PR (or default commit) landed
   the same fix while this one sat open. Evidence: surviving `repo#N` and merge
   OID.
4. **A recreate replaced it.** After the new PR merges, close the original with
   the new PR number and merge OID. Do not wait for the human; this is the
   recreate contract.

Superseded is **not** "discards unique intent." Unique intent still unmet on
default stays `recreate` or `merge_as_is`. Only a close that throws away a live
unmet claim hits the human gate.

Leaving a superseded PR OPEN so the ledger "still has it" is a skill failure.

## Cluster before dispatch

Same shape, same files, or same ticket = **one** cluster, **one** worker. This
overlap is a clustering rule only. It does not create a DAG dependency.

After clustering, every unit starts parallel. Add a DAG edge only when the child
builds on state created or reshaped by its parent (`build-on`), or when the
parent's failure prevents the child's done-condition from being observed
(`masked-verification`). Record that reason in the edge ledger.

Examples that must collapse:

- N CDN SRI / https-pin PRs for one vendor → one recreate
- Two PII-gate PRs for one ticket (`SAH-5119` + draft sibling) → one recreate
- `npm → pnpm` + `pnpm + grype` → one recreate or one close + one recreate
- Pointer-only `config_ref` pins → `merge_as_is` / `rebase_then_merge` if clean,
  else recreate

Do not fan out 1:1 with PR numbers.

## Classify inputs (minimum)

From `scripts/inventory-open-prs.py` plus a skim of title/body:

- number, title, body, author, draft, age days, updated days
- `mergeable`, `mergeStateStatus`
- labels (use as hints: `security`, `incident`, `agent:pause`, `agent:blocked` —
  never as `merge_as_is`). Ignore `agent:needs-human` — not a hold, not a
  recreate trigger, not a `yes` in the human column.
- changed file paths with `pathsComplete: true` and `pathCount == changedFiles`
  (overlap detection)
- additions/deletions

Do not classify from title alone.

## Output table (orchestrator-visible)

```text
#  verdict              cluster              human  why
415 merge_as_is         vite-security        no     CLEAN, dep bump, current
367 recreate            pii-verify-gate      no     DIRTY, overlaps 378
258 hold                ecs-deploy-stage-b   yes    title: DO NOT MERGE
```

Auto-dispatch every `no`. Research every `yes`; then dispatch or hold from that
research. `yes` means research required, not stop-the-drain.
