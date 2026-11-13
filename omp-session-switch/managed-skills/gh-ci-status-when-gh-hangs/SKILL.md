---
name: gh-ci-status-when-gh-hangs
description: "Reading PR/CI status and failed-job logs on this Mac when gh pr view/checks/run view hang or time out, and gh api is refused by the ghx wrapper"
---

Observed 2026-11-09 (dev-profile, dev-env):

- `gh api ...` is refused by the ghx wrapper ("use gh pr view"). `gh pr view/checks/list` and `gh run view --log*` often exceed 20-60s and get promoted to background jobs; output of a job started with `on_complete: wait` is NOT recoverable afterwards. Redirect to a file inside the command, or use the log_path the completion event names.
- Use the `github` tool instead: `search_prs` (state of a PR) and `run_watch` with `repo` + `branch` (jobs, conclusion, commit). `run_watch` on `branch: main` tells you whether main CI was already red before your PR; check that before blaming your change.
- `run_watch` log tails fail with "terminal escape sequences"; `gh run view --log-failed --allow-escape-sequences` and a curl of `/actions/jobs/<id>/logs` both timed out at 60-150s here. If logs stay unreachable, say so and give the run URL rather than guessing the cause.
- dev-env has no GitHub workflows: `run_watch` reports none and PRs merge with no checks. dev-profile CI jobs are `test` and `action` (ubuntu; installs lua5.4 zsh ruby perl tools), so Mac-only repro may not match.
- Local `main` in these repos collects other sessions' direct commits. Before `reset --hard origin/main`, run `git cherry origin/main main` and `git branch -r --contains <sha>`; reset only if every commit is on a remote branch.
- mise config: `bootstrap.symlinks` and `bootstrap.repos.*.sync` are unknown fields; symlinks belong under `[dotfiles."<target>"]` with `mode = "symlink"` and `variants`, and repo sync is implicit in `mise bootstrap --update`.
