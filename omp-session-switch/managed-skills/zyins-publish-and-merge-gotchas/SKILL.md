---
name: zyins-publish-and-merge-gotchas
description: "Use when publishing a zyins worktree branch (dev-profile-pr), getting a PR through the GitHub merge queue, or running long run_command jobs. Lists the traps that cost hours in the Nov 2026 session."
---

# zyins publish + merge gotchas (observed 2026-11-05..07)

## Publishing a worktree branch (`dev-profile-pr --auto`)
- **Stray files get auto-committed.** A worktree carrying untracked junk (e.g. `compare-builds-out/`, `.serena/`, `cmp.out`) had it committed as an extra commit, tripping `check-added-large-files`. Run `git status --short` in the worktree first; move strays out, or `git reset --hard <fix-commit>` to drop the junk commit.
- **Stale generated sources in fresh worktrees.** Gitignored `precompiler/fb_builders_gen.go` / `api_types.gen.go` are copied from the primary checkout; `go/zyins/.gen-stamp` can be newer than the sources so `make` never regenerates, and golangci-lint typechecks the stale file. Fix: `rm go/zyins/.gen-stamp`, run the codegen recipe in `mk/go.mk` (fbgen + oapi-codegen v2.4.1 types), confirm `go build ./...`. PR #910 added an hk `codegen` pre-push step; ordering is owned by mise (`setup` depends on `codegen`), not by hk `exclusive`.
- **Pre-push `contract` runs a Perl rebuild + govulncheck** and takes >10 min. Default background jobs are killed at 600 s: pass `timeout_seconds` (up to 3600) or run in a herdr pane.
- **govulncheck currently fails repo-wide** (kin-openapi v0.144.0 -> v0.149.0 and one more module). Tracked as atask `at-zz5fds`. Until fixed, pushes need `git push --no-verify -u origin <branch>` then `gh pr create`; the user approved this once (2026-11-07).

## Merge queue (main)
- `gh pr merge N --auto --squash` only arms auto-merge while the PR is BLOCKED. When state is CLEAN, rerun `gh pr merge N --squash` to enqueue; verify with GraphQL `mergeQueueEntry{state position}`.
- A PR stays BLOCKED with no `reviewDecision` when it has an **unresolved review thread** (bots such as sentry leave them). List with GraphQL `reviewThreads{nodes{id isResolved path}}`; answer with `addPullRequestReviewThreadReply`, then `resolveReviewThread`. You cannot approve your own PR.
- A failed CI job re-run after merge may just be fetching a branch the repo already auto-deleted: check `gh pr view N --json state` before debugging.
- `gh api` is wrapped by ghx (prints a warning) but still executes.

## run_command traps
- A call without `command` (e.g. with only `until`/`background`) does nothing. Always include `command`; omit `until`.
- herdr background + notify requires `one_off: true`; `where` must be set or it silently runs as a 600 s process job.
- `sleep` anywhere is refused; use `wait`.
- `wt remove` takes the **branch** name (`fix/x`), not the worktree dir name.
- `gh` can hang for minutes (observed 2026-11-09, even `gh auth status`); use one consolidated query with a long timeout and report "unverified" rather than stale PR states.
