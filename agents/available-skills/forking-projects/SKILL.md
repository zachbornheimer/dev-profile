---
name: forking-projects
description: Use before forking a project, and whenever a fork needs structure or repair - deciding fork vs plugin vs upstream PR, choosing what `main` holds (pristine mirror vs upstream plus a carry commit), sorting changes into upstream-bound / personal / outside-the-source, designing the branch manifest, keeping the fork synced, or untangling a fork that has too many branches, stacked branches, or a build that skips or fails. Make sure to use this whenever the user says fork, upstream, mirror, carry patch, "our main", "submit a PR upstream", or asks why a fork build is hard to keep working, even if they never say "fork strategy". The live procedures for the omp fork (zachbornheimer/oh-my-pi) are in `updating-oh-my-pi`; this skill is the why and the design.
---

# Forking projects: when, why, and how to keep it cheap

A fork costs something every time upstream moves. The goal is to keep the delta small, keep every piece of it explainable, and make syncing boring. Decide in this order; each step can remove the need for the next.

## 1. Do you need a fork at all?

Try these before any fork, cheapest first:

1. **Config or plugin point.** Does the project load tools, hooks, skills or settings from a user directory? Then your change is files in your own repo, not a patch to theirs.
2. **Upstream PR only.** If the change is generally useful, send it and wait. A fork is the bridge until it merges, not the destination.
3. **Fork.** Only for behavior upstream will not take or has not taken yet.

**Worked example (omp).** Three bot commits registered 130 branches (67, 46, 17), most of them `tools/<name>`, in a 150-entry manifest. The one I diffed adds only new files under `.omp/tools/<name>/`. Stock omp discovers custom tools in `~/.omp/agent/tools` and `.omp/tools` (`omp://custom-tools.md`), so those tools need no fork (`creating-new-tools` owns how they are generated). Each one cost a fetch, a merge and a conflict risk on every build for no benefit. I read only the first 300 of 2,721 lines of one diff, so check that a branch touches nothing outside its tool directory before moving it.

## 2. Sort every change into one of three kinds

| Kind               | Test                                                                 | Where it lives                                                       |
| ------------------ | -------------------------------------------------------------------- | -------------------------------------------------------------------- |
| Outside the source | A plugin, custom tool, skill, hook or config can do it               | Your own repo or user directory. Not in the fork.                    |
| Upstream-bound     | A maintainer could reasonably accept it                              | Its own branch, cut from `upstream/main`, one concern, with tests    |
| Personal           | Tied to your gateway, identity or taste; upstream will never want it | A few themed branches or the carry commit. Not one branch per tweak. |

Why per-kind: an upstream-bound change must be PR-clean, which constrains its base and contents. A personal change has no such constraint, so extra granularity only adds merge steps.

## 3. Choose what `main` holds

| Model           | `main` is                                       | Sync is                      | Pick it when                                                                                                                                  |
| --------------- | ----------------------------------------------- | ---------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| Pristine mirror | Exact copy of `upstream/main`                   | Fast-forward                 | You send many PRs upstream, or compose many topic branches into a build                                                                       |
| Carry on main   | Upstream plus a small, isolated carry delta     | Merge from upstream          | Your delta is small and stable: a build workflow, config, a few patches                                                                       |
| Patch stack     | Upstream release tag plus ordered carry commits | Rebase onto each new release | Long-lived vendor fork that tracks releases, like OpenShift's Kubernetes (`UPSTREAM: <carry>:` commits, picked onto a new branch per release) |

All three work. The sources I read agree on the rules below, not on one model: GitHub's sync docs assume local changes live on the default branch, the kbralten maintainer gist keeps `base` pristine and builds from a disposable integration branch, and OpenShift carries tagged commits.

**What forces the choice for most personal forks:** GitHub fires `schedule` events only from the default branch, so a scheduled build needs its workflow file there. A pristine-mirror `main` therefore forces a second default branch (the old omp `ci` branch), which surprises everyone who opens the repo. If the only carry is the workflow, a resolver and a README, carry on `main` removes that branch. Chosen for omp: carry on main. See "omp status" below for what is live.

## 4. Rules that hold in every model

- **Never force-push a shared branch.** Merge or cherry-pick. A rewritten public branch breaks everyone's checkout and every open PR.
- **Cut upstream-bound branches from `upstream/main`, never from your `main`.** Your carry commit must not appear in the PR diff. A PR from a fork branch against upstream is fine from any base.
- **One concern per branch, never stacked on another topic branch.** Stacked branches contain each other, so a PR from one carries the others' commits, and one conflict with upstream fails the whole chain. Where a real dependency exists, record it as an order and PR the base first.
- **Isolate the carry.** Put everything you add under one directory upstream does not have, with file names upstream will not use. Then syncs never conflict there. The workflow file in `.github/workflows/` is the one unavoidable exception; give it a unique name.
- **Disable upstream's own workflows** in the fork's Actions settings if they come back with `main`.
- **Integration branches (`omp-build`, `assembled`, `next`, `seen`) are throw-away or merge-only — never commit or cherry-pick directly onto them (`gitworkflows(7)`).** Every feature or fix lives on its own topic branch (`feat/<slug>` or `fix/<slug>`). Enforced at two layers across every fork: `main-branch-guard.py` (`PreToolUse` denies `git commit`, `git cherry-pick`, `git rebase`, `wt step commit`, and non-merge pushes to `assembled`/`next`/`seen` unless `MERGE_HEAD` is present) and `.git/hooks/reference-transaction` (installed by `bin/dev-profile-omp-machine-setup`, which rejects any non-merge update to `refs/heads/assembled`, `refs/heads/next`, or `refs/heads/seen`).
- **Resolve cross-branch textual conflicts via `git rerere` (`--rerere-autoupdate`), not by merging topic branch A into topic branch B (`howto/maintain-git.adoc`, `git-rerere(1)`).** Merging topic A into topic B contaminates B's upstream PR diff. Instead, seed `.omp-build/rr-cache` from prior merge commits (`contrib/rerere-train.sh`), enable `rerere.enabled=true` and `rerere.autoupdate=true` in the ephemeral assembly step (`git merge --no-ff --no-edit --rerere-autoupdate`), and use `refs/merge-fix/<branch>` (or `.omp-build/merge-fix/<branch>.patch`) for semantic-only conflicts.
- **Give every carried branch a reason in plain English.** A branch nobody can explain is the first one to delete.
- **A branch upstream has merged is deleted.** Detect it: `git merge-base --is-ancestor <branch> upstream/main`, or `git cherry upstream/main <branch>` printing only `-` lines.

## 5. The branch manifest

When a build merges many branches, the list is the single source of truth. Format and the migration order are in `references/branch-manifest.md`. The design in one line each:

- **One file per branch**, path = branch name (`branches/fix/native-build-cargo.toml`), so two agents adding different branches never touch the same file and a duplicate is a visible conflict.
- **No shared list, no hand-ordered array.** A single JSON array or JSONL file collides when two writers append at the end.
- **The resolver enforces the rules**: reason required, branch exists, valid `upstream` status, merged branches flagged for deletion.

## 6. Keep the fork current without you

Sync and build are two jobs. Automate both, or the one you skipped becomes the gap.

- **Observed on the omp fork:** the daily cron fired about 8 hours late, and the hourly cron fired about 2 of 14 slots. GitHub's `schedule` is best-effort. Do not treat it as a clock; add a manual dispatch and a way to see that a run happened.
- **Nothing synced `main`.** The build ran overnight on a `main` that was 83 commits behind, because syncing was a manual script and no job called it. If `main` has a ruleset, a workflow's own token cannot update it. A local launchd job running the sync script, or a workflow with a stored admin token, is the choice; the token loosens protection, so say so.
- **`GITHUB_TOKEN` cannot push changes to workflow files** (GitHub's documented limit; not tested here). A sync that pulls in an upstream workflow change can fail for that reason, so run the sync with a different credential.

## 7. Verify, never assume

A fork is healthy only when these are measured, not inferred:

1. How far `main` is behind `upstream/main`: `git rev-list --count main..upstream/main`.
2. The latest release's recorded build commit contains upstream's tip and every manifest branch: `git merge-base --is-ancestor <ref> <build_commit>` for each.
3. The running binary reports that build. For omp: `omp --version` prints `github.com/zachbornheimer/oh-my-pi@build-...`.
4. A skipped build was skipped for the right reason. omp skips when the assembled tree equals the last release's tree, so "skipped" can mean "nothing changed" and still look like a failure.

## 8. Failure modes seen on the omp fork

- **Stack of nine branches** conflicting with about 700 upstream commits at once; one conflict failed the build. Fix: merge forward once, then keep branches independent.
- **Generated registrations.** A pipeline added 130 per-tool entries overnight under the user's name. Make generators write files into a tools directory, not register branches.
- **Stale local checkout.** A worktree listed 11 branches while the fork's live branch listed 19. Read the remote, not the checkout.
- **A pinned runner label was retired** (`macos-14`, 2026-11-02) and the darwin job failed. Use the moving label (`macos-latest`) for the runner, and pin everything else.
- **Claims without a measurement.** Twice I stated a cause before checking it (a 05:00 sync that "should" have updated the binary; a 20-branch check that was really 150). Measure first.

## omp status

Live today: `main` is an exact upstream mirror, `ci` is the default branch and holds the workflow, `BRANCH_MANIFEST` is a JSON block in the workflow, and builds poll hourly. Chosen direction, not yet migrated: carry on `main`, manifest as one TOML file per branch, `tools/*` moved out of the fork, upstream-bound branches split off `steering-fixes`. Until that lands, follow `updating-oh-my-pi` for every command; it describes the live layout. When the migration lands, update both skills in the same change so neither describes a state that is not live.
