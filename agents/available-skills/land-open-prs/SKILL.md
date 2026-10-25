---
name: land-open-prs
description: Use when draining open PRs onto main, landing a PR backlog, merging unmerged
  PRs, recreating stale or conflicted branches, or when the user says
  /land-open-prs, "get these PRs merged", "get all prs merged", "You should get all branches merged in, all prs merged in", "let's get everything on main now", "PRs that are superseded should be identified and closed", or "inventory open PRs and land them."
---

# Land Open PRs

Every initially open PR ends **MERGED**, **CLOSED** with a recorded rationale,
or **OPEN** only on a named `hold`. A merge is complete only when its explicit
merge commit OID is proven to be an ancestor of the repository's default branch.
Labels are not evidence. The original branch is not owed a merge.

**Single repo only.** This skill operates on exactly the repo named at
invocation (or the current directory's repo if none is named). Never create,
push to, or merge in any other repo — not even to fix a lookalike PR in a
sibling repo, and not even when a dependency-upgrade or conformance-sync
cluster obviously has a twin elsewhere. Name the sibling repo in the final
report as out-of-scope instead.

**Default operating mode is no-questions.** Once inventory and classification
are done and the table is presented, run to completion without pausing for
confirmation — AskUserQuestion is reserved for a genuine fork this skill's own
human gate can't resolve (see below), not for "does this look right?" checks.
Bias toward landing the maximum number of PRs safely: auto-dispatch every
`no`-row cluster, research every `yes`-row against live state then dispatch or
hold from that research, and keep moving through the rest even when one cluster
blocks or a hold comes up. A hold is a named, evidenced stop on that one PR —
it is not a reason to pause the whole drain and ask the human what to do next.
`agent:needs-human` is ignored (not a hold, not a recreate trigger).

**REQUIRED SUB-SKILLS:** `prompt-writer`, `create-dag`, `code-construction`,
`agnostic-facades`, `dependency-upgrade`, `babysit-pr`, `status-report`. Load
`pr-review` only if you must re-walk a diff; do not run its merge verdict in
place of this lander.

## Gotchas (defaults this skill exists to break)

<!-- markdownlint-disable MD013 -->

| Excuse                                            | Reality                                                                                                                                                        |
| ------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| "`ready-to-merge` / green / Devin said ship"      | Read the diff, threads, and mergeability. Labels lie.                                                                                                          |
| "False positive — I'll reply and resolve"         | Rebut only with recorded reproduction, a targeted test, or an authoritative contract. If ambiguity remains, rewrite.                                           |
| "Rebase the 60-day-old branch"                    | Recreate from current default. Take intent + tests, not the conflict pile.                                                                                     |
| "That failing test isn't this PR"                 | Reproduce on default. A real default-branch failure becomes a separate repair PR and DAG blocker; otherwise hold with evidence.                                |
| "Actions is down, force-merge"                    | Local `mise run ci` is proof. It does not satisfy a required GitHub check. Hold.                                                                               |
| "I'll merge from this checkout"                   | Worktree per cluster. Session tree stays on its branch.                                                                                                        |
| "Ten morris SRI PRs, ten workers"                 | Same shape = one cluster, one recreate.                                                                                                                        |
| "babysit-pr allows any rebuttal"                  | This skill permits only recorded reproduction, targeted-test, or authoritative-contract evidence; ambiguity is rewritten.                                      |
| "Leave the old PR open; the recreate replaces it" | Identify superseded PRs during classify and **close** them. Comment the surviving PR/OID or default SHA. See [references/verdicts.md](references/verdicts.md). |
| "Human-gate row → auto-hold"                      | Research live state first; hold only when research cannot decide or the owner-only list applies.                                                               |
| "`agent:needs-human` means hold"                  | Ignore it. Existing `agent:pause` / `agent:blocked` hints still apply.                                                                                         |
| "Serialize every merge through one lock"          | Independent clusters merge in parallel. Serialize only on ledger edges.                                                                                        |
| "Rebase — it's only a few merges behind"          | More than one merge behind current default → abort and recreate; do not conflict-resolve.                                                                      |
| "Default is red; keep landing siblings"           | Halt sibling merges, repair, record a `masked-verification` edge, then resume.                                                                                 |
| "Worktree branches aren't PRs — skip them"        | Worktree branches are in scope. Land them here (or `wt` from that worktree).                                                                                   |

<!-- markdownlint-enable MD013 -->

## Spine

1. **Inventory** — `scripts/inventory-open-prs.py [owner/repo]`. JSON on stdout;
   diagnostics only on stderr. `ghx` only. The command paginates every open-PR
   and per-PR file page, then repeats the exhaustive open-PR observation.
   `inventoryComplete: true` means the full ordered cohort matched before and
   after detail/file collection, `openPrCount` matches that cohort, and every PR
   has `pathsComplete: true` with `pathCount == changedFiles`. This is a stable
   cohort check, not an atomic GitHub snapshot. Any observed membership or order
   change fails closed and requires a rerun.
2. **Classify** — one sonnet worker, read-only. Verdicts in
   [references/verdicts.md](references/verdicts.md). Superseded identification
   is mandatory: compare each PR's intent to current default and to the rest of
   the open cohort; superseded PRs are `close`, not leftovers. Ignore
   `agent:needs-human`. Present the table, then auto-dispatch every `no` and
   research every `yes` (see Human gate). Duplicate, no-op, explicitly
   abandoned, and superseded closes auto-dispatch and end **CLOSED** with a
   rationale.
3. **Schedule** — `create-dag`. Parallel is the null hypothesis. File overlap
   clusters work but does not create an edge. Edges only for `build-on` or
   `masked-verification` (including a shared GitHub Actions `concurrency` group
   that would cancel a sibling — the child's checks cannot be observed GREEN
   while the sibling occupies the group). Record evidence in the edge ledger.
4. **Dispatch waves** — spawn every independent DAG root in the _current_ wave
   at once, each in its own worktree. No artificial serial cap. Host live-child
   limits may queue extras; do not manually serialize independent roots.
   - Wave A: `close` (superseded / duplicate / no-op / abandoned).
   - Wave B: `merge_as_is` and `rebase_then_merge`.
   - Wave C: `recreate`, including researched former human-gate items.
     Independent clusters **merge in parallel**. Do not funnel every merge through
     one lock or one merge-agent. Serialize only on ledger edges.
     `prompt-writer` compiles each `/goal`. Implement workers: `isolation:
     "worktree"`, explicit model (haiku mechanical, sonnet otherwise). Never
     inherit Opus for a walk.
5. **Land** — the bar below, then `babysit-pr` for CI watch + auto-merge +
   `state: MERGED`. After each merge: fetch default, prove the explicit merge
   OID is an ancestor, observe default required checks (GitHub, or `mise run ci`
   when GitHub is not the gate). If default is red, **halt sibling merges**,
   open/merge a repair, record a `masked-verification` edge, then resume. If a
   worker's base is **more than one merge** behind current default, abort that
   worker and recreate from current default; do not conflict-resolve.
6. **Report** — `status-report`. The final ledger contains every PR from the
   initial inventory exactly once. Every `[OK]` names `repo#N`, the explicit
   merge commit OID, and its default-branch ancestry proof; every `CLOSED` names
   its rationale; every remaining `OPEN` names its hold.

## Per-PR lander (the bar)

Do this on the PR that will actually merge (the recreate, not the stale
original).

0. **Applicability check, skeptical by default.** Before recreating anything,
   re-verify the PR's premise still holds against the CURRENT default branch —
   not against its stale base. Diff what it proposes against what's actually
   on default today: another PR may have already shipped the same or a
   conflicting change, the file it targets may no longer exist, or the
   convention it enforces may have been intentionally superseded (e.g. an
   automated conformance/autofix bot moved the target state since this PR
   opened). If the PR's target state already matches default, or default has
   moved to a different intentional state, this is a **no-op close** with the
   diff comparison as evidence — do not recreate a PR that would immediately
   fail CI by asserting a doctrine default no longer follows, and do not guess
   which doctrine is "right" when that's a policy call for the concept's
   owner. Only proceed to recreate once you've confirmed the PR's intent is
   still live and unmet on default.
1. **Read the record.** Description, every review thread (open and resolved),
   every issue comment, every bot login. Diff is ground truth. `ghx`.
2. **Adversarial review** — fresh-context `reviewer`. Contract:
   [references/adversarial-review.md](references/adversarial-review.md).
   Findings are a to-do list, not a survey.
3. **Act.** `prompt-writer` → `implement`. Load `code-construction` on any body
   change. Load `dependency-upgrade` on any manifest/lockfile bump (changelog,
   baseline tests, call-site grep, facade if >2 call sites). Load
   `agnostic-facades` when the diff talks to a vendor, SDK, queue, store, or
   names a provider.
4. **Threads.** Real defect → fix. A rebuttal may close a finding only when the
   PR records one of: a reproduction that disproves it, a targeted test that
   exercises it, or an authoritative contract that settles it. Rewrite any
   remaining ambiguity so a junior cannot hit the same trap, then
   `resolveReviewThread`.
5. **Checks.** `ghx pr checks`. Every check terminal and green. For a failure
   claimed to be unrelated, reproduce the exact failure on current default.
   - Reproduced on default → open and merge a separate repair PR, record a
     `masked-verification` DAG edge from repair to blocked PR, then rerun the
     blocked PR's checks.
   - Not reproduced on default → leave this PR **OPEN** on a named hold with the
     commands, SHAs, and outputs that prove the comparison. Do not waive red.
   - GitHub cannot run checks (outage, Actions disabled, checks never queued) →
     `mise run ci` in the worktree, paste the output on the PR.
   - If the ruleset **requires** GitHub check runs, local green is not enough:
     **hold**. Do not `force-merge`. `belt pr force-merge` is owner-only; name
     it, do not run it.
6. **Stale-base abort.** If this worker's base is more than one merge behind
   current default, abort and recreate from current default; do not
   conflict-resolve.
7. **Pre-merge refresh.** Immediately before merge, re-query mergeability,
   required checks, head SHA, and default SHA. If they disagree with classify,
   re-evaluate. Do not merge on stale classify data.
8. **Merge.** Zero open threads + green (GitHub, or local-as-gate when no
   required GitHub checks) → `babysit-pr` auto-merge. `merge_as_is` and
   `rebase_then_merge` are eligible only when `baseRefName == defaultBranch`.
   Query `mergeCommit.oid` explicitly, poll until `state: MERGED`, fetch the
   current default branch, and prove that OID is its ancestor. Close superseded
   originals with a rationale linking the surviving PR and merge OID.
9. **Post-merge default CI.** Observe default required checks (GitHub, or
   `mise run ci` when GitHub is not the gate). Red → halt sibling merges, open
   and merge a repair, record a `masked-verification` edge, then resume.

Worker slots: [references/worker-order.md](references/worker-order.md).

## Human gate

Two tiers. `agent:needs-human` is ignored in both.

**Research, then dispatch** — observe live state (API, current default, the
repo's ADR/runbook) and the relevant standard. If the need is real and unmet,
land the standard-shaped change. Hold only if research cannot decide:

- Breaking public contract
- Production access, permissions, deploy, auth, money, or live-key path
- Consequential change: confirm a proven rollback exists; if none, hold

**Owner-only hold** — do not dispatch; AskUserQuestion only if this list cannot
resolve it:

- Title or body says do-not-merge / needs sign-off
- Irreversible data mutation or deletion with no proven rollback
- Two surviving product intents in one cluster
- Close that discards unique intent (not superseded)
- Required GitHub checks cannot run

Everything else auto-dispatches.

## Done

Re-inventory open PRs exhaustively. Only named holds may remain **OPEN**; a
`close` verdict is **CLOSED** with its rationale and surviving PR/OID when one
exists. The final ledger accounts for every initially inventoried PR. Every
landed PR has `mergedAt`, an explicitly queried `mergeCommit.oid`, and proof
that the OID is an ancestor of current default in-transcript. Default-branch
required checks are green (GitHub, or `mise run ci` when GitHub is not the
gate). If the repo has a production surface, it is still serving after the drain
(the repo's documented health/ready probe, observed). A red default that would
deploy is not done.
