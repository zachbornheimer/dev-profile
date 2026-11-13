---
name: sah-pr-landing-gotchas
description: "Use when landing Software-Automation-Holdings-LLC PRs (isa-platform, zyins, platform) through fix_red_ci, the merge queue, or local pre-push hooks on the Mac; lists what fix_red_ci cannot do and the known local hook breakages"
---

# Landing SAH PRs: gotchas (observed 2026-11-09)

## fix_red_ci cannot do these, so do them by hand
Its model has no tools and never sees repository files. It only sees CI logs, threads and comments.
- **Draft PR:** it returns `impossible, 0 rounds`. Run `gh pr ready N` first.
- **Base conflict:** it returns `impossible`. Merge `origin/main` into the branch yourself, without force-pushing.
- **Review thread that needs code context** (for example a Sentry bug prediction): it returns `impossible` ("needs exact existing text"). Read the file and fix it yourself. Then reply to the thread and resolve it through GraphQL with `addPullRequestReviewThreadReply` and `resolveReviewThread`.
- **Design docs:** it may push *content* rewrites to them. On isa-platform #763 it weakened an owner decision. Always diff what it pushed (`git log <old>..origin/<branch>`) before letting the PR merge, and report any changed decision text.

## Merge queue (isa-platform and zyins main)
- `gh pr merge N --auto --squash` prints "The merge strategy for main is set by the merge queue". That message is not an error.
  - If the PR is CLEAN, it enqueues directly and `autoMergeRequest` stays null.
  - If the PR is not CLEAN, it arms auto-merge.
  - Confirm either way with GraphQL `pullRequest{isInMergeQueue mergeQueueEntry{state position}}`.
- A push to a new head can drop an armed auto-merge. Re-run `gh pr merge --auto` after the PR turns CLEAN.

## Local Mac hook breakages and their fixes
- **`gh` hangs inside `run_command`** (more than 90 s, timed out). The same `gh` call runs in under 2 s from the Python eval (`subprocess`). Use eval for `gh`.
- **Pre-push fails with `mise ✗ navi/upx … unsupported env: darwin/arm64`.** Upstream ships no macOS builds of either. Homebrew provides them on the Mac. In `~/.config/mise/config.toml`, use `{ version = ..., os = ["linux", "windows"] }` for both. Already applied.
- **`dotnet test packages/csharp/Isa.Sdk.sln` fails locally** while CI passes. The mise dotnet `8.0` pin resolves to SDK 8.0.427, which needs runtime 8.0.33 and targeting pack 8.0.33.
  - Install the runtime tarball into `~/.local/share/mise/dotnet-root/`.
  - Extract the `microsoft.netcore.app.ref` nupkg. Copy its `data/`, `ref/net8.0/` **and** `analyzers/` into `packs/Microsoft.NETCore.App.Ref/<ver>/`. Missing `analyzers/` gives CS0006.
- **Tracked `tests/conformance/tools/__pycache__/*.pyc` in isa-platform** get rewritten by hooks and cause add/add conflicts. On merge, keep main's copies (`git checkout --theirs`), and `git checkout --` them before committing.
- **`platform` repo `test/profile.test.pkl-expected.pcf` is generated.** On a conflict, take main's copy, then run `mise x pkl -- pkl test test/profile.test.pkl --overwrite`. Never hand-merge it.
- **Pre-commit hooks in isa-platform can exceed 300 s.** Run commits as background `run_command` jobs. A timed-out foreground commit may still complete, so check `git log -1` before retrying (a retry fails with "cannot lock ref HEAD").

Action boundary: the "ready, merge main, fix the thread, enqueue" sequence belongs in fix_red_ci and make_pr_mergable as code. Retire this skill once those handle drafts, conflicts and file context.
