# Worker orders

Every dispatched unit is a `/goal` from `prompt-writer`. Fill every slot. Point
at skills; do not paste them.

## Isolation and model

- Classify / adversarial review: read-only, `reviewer` or `explore`, model
  `sonnet` (haiku for inventory skim only).
- Implement / recreate / rebase: `implement`, `isolation: "worktree"`, model
  `sonnet` (haiku for mechanical identical-shape edits: SRI pins, pointer SHA
  bumps).
- Never inherit the orchestrator model. Never Opus for a CI/browser walk.

Worktrees: `~/Developer/<Org>/.worktrees/<repo>-<slug>/`.

## Dispatch

Spawn every independent DAG root in the current wave at once, each in its own
worktree. No artificial serial cap. Host live-child limits may queue extras; do
not manually serialize independent roots. Serialize only on ledger edges.
Independent clusters merge in parallel — do not funnel merges through one lock
or one merge-agent.

Wave order: A `close` → B `merge_as_is` / `rebase_then_merge` → C `recreate`
(including researched former human-gate items).

## Recreate order (default under uncertainty)

- **intent:** Land `<claim>` on current default as a new PR; close `<old#>` as
  superseded after merge.
- **target:** `wt switch --create <branch> --base origin/<default> --no-cd`;
  files the old diff meant to change, rewritten to current tree.
- **blast-radius:** do not carry unrelated commits from the old branch; do not
  edit the session checkout.
- **inputs:** old PR number, body, adversarial FINDINGS, changed-path list, this
  skill's lander bar.
- **done-when:** `ghx pr view <new> --json state,mergedAt,mergeCommit` shows
  `MERGED` with an explicit `mergeCommit.oid`; that OID is proven an ancestor of
  current default; `ghx pr view <old> --json state` is `CLOSED` with the
  supersession rationale recorded; `mise run ci` exited 0 in the worktree
  (in-transcript).
- **verify-how:** lander bar + `babysit-pr` merge confirmation.
- **protocols:** `code-construction` always. `dependency-upgrade` if any
  manifest/lockfile. `agnostic-facades` if a vendor/SDK/queue/store is named or
  called.

Port intent and tests. Do not replay the old conflict resolution.

## Rebase / merge-as-is order

Same lander bar on the existing PR. Require `baseRefName == defaultBranch`.
Rebase onto current default: `git fetch origin <default>` then
`wt step rebase origin/<default>` then
`git push --force-with-lease -u origin <branch>`.
If the rebase is structural (premise dead), convert to `recreate` — do not
hand-merge conflicts to "save" the branch. If the base is **more than one merge**
behind current default, abort and recreate from current default; do not
conflict-resolve.
After merge, query `mergeCommit.oid` explicitly and prove it is an ancestor of
fetched current default.

## Lander steps the order must name

1. Adversarial review (this skill's four questions) → act on FINDINGS.
2. Every review thread resolved. An evidence-backed rebuttal must record a
   reproduction, targeted test, or authoritative contract; ambiguity is
   rewritten.
3. All checks green. Reproduce an allegedly unrelated red on current default: if
   red there, merge a separate repair PR first and record its
   `masked-verification` DAG edge; if green there, leave the blocked PR open on
   a named hold with comparison evidence. Use local `mise run ci` if GitHub
   cannot run checks.
4. Hold (do not force-merge) when a required GitHub check cannot run.
5. Stale-base abort: more than one merge behind current default → abort and
   recreate; do not conflict-resolve.
6. Pre-merge refresh: re-query mergeability, required checks, head SHA, and
   default SHA; re-evaluate if they disagree with classify.
7. `babysit-pr` auto-merge; explicitly query `mergeCommit.oid`, confirm
   `state: MERGED`, and prove default-branch ancestry.
8. Post-merge: observe default required checks (GitHub, or `mise run ci` when
   GitHub is not the gate). Red → halt sibling merges, repair, record a
   `masked-verification` edge, then resume.

The final order must emit a ledger row for every PR in the initial inventory:
`MERGED` with OID and ancestry proof, `CLOSED` with rationale, or `OPEN` with a
named hold. A `close` verdict is not an open leftover. Superseded originals
must be **CLOSED** (comment + surviving PR/OID or default SHA), not left OPEN
because a recreate exists. See [verdicts.md](verdicts.md).

## `/goal` bound

Turn cap and token budget on every order. Classify: 8 turns. Mechanical
recreate: 20. Product recreate: 40. Lander+babysit: 30 plus babysit-pr's own
watch loop.
