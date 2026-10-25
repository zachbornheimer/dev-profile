---
name: split-to-prs
description: Split a branch, stash, or pile of changes into small reviewable PRs. Use when asked to split a diff, branch, or chat history into PRs. Distinct from babysit-pr, which monitors execution after PRs are open.
---

# Split to PRs

Turn one pile of work into a few small, independently mergeable PRs. Plan is
approved before any branch is created; the working tree is never touched without
a recoverable snapshot.

## Hard rules (never violate)

- **No branch, commit, push, or PR until the user approves the plan.** Propose first; act after.
- **Snapshot before moving anything.** Even when work is dirty on `main`, save a
  recoverable ref before touching the tree:
  ```bash
  SHA=$(git stash create "pre-split")
  [ -n "$SHA" ] && git update-ref "refs/backup/pre-split-$(date +%s)" "$SHA"
  ```
- **Stage with `wt step commit`, never `git add PATH`.** `git add .` / `git add -A`
  is forbidden — it silently includes unintended files.
- **Independent PRs off the default branch by default.** Stack only when the
  dependency is _provably_ real (B cannot be tested without A). If in doubt, they
  are independent.
- **No destructive git commands** (`reset --hard`, `clean -fdx`, branch deletion,
  force-push, history rewrite) without explicit approval. Branch deletion, if
  ever approved, is `wt remove`.

## Step 1 — Check the state

Compare current work to the default branch (committed + uncommitted). Use chat
history to recover intent when context is thin. Before proposing slices, find
ownership signals (`CODEOWNERS`, nested ownership files, `tools/ownership/`) and
flag any path that crosses reviewer-boundary lines.

## Step 2 — Propose the split

Usually PR titles are enough. Add a one-line scope note only when a title is
ambiguous. Show a Mermaid dependency diagram when there are more than two slices
or any stacking. Optimize for: reviewer-aligned (one owner per PR), minimal
unrelated diff, foundations before consumers.

Ask for approval. Do not proceed to Step 3 until you have it.

## Step 3 — Execute (after approval)

For each approved slice, in order:

1. `wt switch --create <slice-branch> --base <default> --no-cd`
2. Apply only the planned files onto that clean worktree.
3. `wt step commit`, then `git push -u origin <slice-branch>`, open the PR.

## Step 4 — Report back

PR titles + URLs, plus a note on what (if anything) remains on the original
branch or working tree. Do not delete the backup ref or the original branch
unless asked.

## Gotchas

- **Ownership conflicts.** A slice that mixes paths owned by two teams will stall in
  review — split along CODEOWNERS lines before proposing.
- **"Independent" is often wrong.** Shared types, shared fixtures, shared init —
  check for hidden coupling before declaring independence.
- **The backup ref is the parachute.** Confirm it exists before you start rewriting
  branches. A lost ref is a data loss incident.
