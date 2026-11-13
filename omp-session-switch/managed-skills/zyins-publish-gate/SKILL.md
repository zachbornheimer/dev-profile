---
name: zyins-publish-gate
description: "Use when publishing a zyins branch through dev-profile-pr/hk's pre-push contract, when that publish fails on the gate, or when a zyins PR sits BLOCKED in the merge queue."
---

# Publishing a zyins branch (and getting it merged)

## Publish

```sh
S=~/Developer/Software-Automation-Holdings/.worktrees/zyins-<slug>
cd "$S" && dev-profile-pr --auto > /tmp/publish-$SLUG.log 2>&1
```

Run it in a herdr pane, not a process job: the contract's Perl bootstrap can exceed
the 600 s job cap and a kill lands mid-`cpanm`, so the next run redoes it.

```json
{"command": "...", "background": {"where": "herdr", "target": "tab", "one_off": true, "on_complete": "notify"}}
```

`one_off` is required for `on_complete: notify` on a herdr pane; without it the call
errors. Do not pass `until` to `run_command` — a call with `until` and no `command`
just waits out the clock and runs nothing.

## Traps that actually bite

| Symptom | Cause | Fix |
|---|---|---|
| `golangci-lint` fails on an undefined field (`CelWhen`, `req.Sex`) | Fresh worktree inherited gitignored `precompiler/fb_builders_gen.go` / `server/api_types.gen.go` from the primary checkout, and `.gen-stamp` arrived newer than the sources, so `make` never regenerates | `rm go/zyins/.gen-stamp`, run the codegen recipe (fbgen builders/converters + `oapi-codegen -generate types`), confirm `go build ./...` |
| `check-added-large-files` flags `compare-builds-out/`, `.serena/`, `cmp.out` | Strays in the worktree got auto-committed into a junk commit on top of the fix | `git reset --hard <fix-sha>`, then move strays out of the worktree before publishing |
| `scan` step fails: govulncheck | Repo-wide dependency vulns in `main`, not the branch | Needs a dependency bump (`mise run scan` as proof); `--no-verify` only when the user says so |
| Publish dies ~600 s in, last log line is a `cpanm` module | Job cap | herdr `one_off` (above); `.perl5` survives and the next run resumes |
| Workflow job fails on `git fetch +refs/heads/<branch>*` | Branch deleted after merge (repo auto-deletes) | Nothing to fix: check `gh pr view <n> --json state` first — it is usually already MERGED |

## Getting the PR merged

`main` uses a merge queue. `/tmp` loop:

```sh
gh pr view <n> --json state,mergeable,mergeStateStatus,autoMergeRequest
```

- `BLOCKED` + `reviewDecision` empty ⇒ look for unresolved review threads, not reviews:
  ```sh
  gh api graphql -f query='{repository(owner:"Software-Automation-Holdings-LLC",name:"zyins"){pullRequest(number:<n>){reviewThreads(first:20){nodes{id isResolved path comments(first:1){nodes{author{login} body}}}}}}}'
  ```
  Reply with `addPullRequestReviewThreadReply`, then `resolveReviewThread`. State goes
  `CLEAN` immediately.
- Unresolved bot thread ⇒ answer the substance, do not just resolve it. Sentry-style
  claims about `hk.pkl` ordering: the ordering owner is `mise.toml` (`setup` depends on
  `codegen`), `exclusive = true` only stops two runs racing.
- Self-approval is impossible: `gh pr review --approve` fails on your own PR.
- Once `CLEAN`, `gh pr merge <n> --squash` *enqueues* it. "already queued" plus
  `mergeQueueEntry.state = AWAITING_CHECKS, position 1` is success; stop calling.
- `gh api repos/:owner/:repo/branches/main/protection` returns nulls here (ghx wrapper);
  trust `mergeStateStatus` and GraphQL instead.

## Cleanup after merge

```sh
wt step prune                       # merged worktrees
wt remove <branch> --force          # by BRANCH name, not worktree name
```
