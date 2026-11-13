---
name: landing-dev-profile-main-commits
description: "Use when local commits on dev-profile main must reach origin and a direct push to main is refused by the main-branch guard, or wt land/wt pr say nothing to do."
---

Direct `git push origin main` in ~/Developer/Personal/dev-profile is refused (main-branch guard). `wt land` and `wt pr` do nothing when the commits are already on local main ("already integrated into main").

Procedure that worked:
1. `export GITHUB_TOKEN="$(gh auth token)" GH_TOKEN="$(gh auth token)"`.
2. `wt switch --create chore/land-local-main --base main --no-cd -y` (worktree at ../.worktrees/dev-profile-chore-land-local-main).
3. From that worktree: `git push origin HEAD:refs/heads/chore/land-local-main`. Run it in the background; pre-push hooks take minutes. If a hook fails on a file from someone else's commit (e.g. a script missing its exec bit), fix it with a small commit in this branch and push again.
4. `gh pr create --repo zachbornheimer/dev-profile --base main --head chore/land-local-main ...`.
5. `gh pr merge <n> --merge --auto`. Branch policy blocks an immediate merge; auto-merge waits for checks (~10 min). Never use `--admin` without the user's approval.

Local main may be rebased by other sessions, so commit SHAs change; refer to commits by subject.

Observed failure modes (2026-11-09/10 session):

- **Stale branch from a prior session:** step 2 fails with "Branch chore/land-local-main already exists". Switch without `--create`, then if the worktree tip is not local main: `git reset --hard main`, and push with `git push --force-with-lease=chore/land-local-main:origin/chore/land-local-main origin HEAD:refs/heads/chore/land-local-main`.
- **`gh pr create` fails silently:** network flaps ("error connecting to api.github.com") can make it exit with no output while the PR was still created. Before retrying create, check first: `gh pr list --repo zachbornheimer/dev-profile --head chore/land-local-main --state open --json number`. api.github.com outages were transient; retry after ~30s.
- **Long commands:** start pushes, `gh pr create`, and merge-watch with `background` and settle each with `wait {job_id}`; `gh` calls frequently exceed the 20s foreground budget. In poll loops use `/bin/sleep` (bare `sleep` gets rewritten by run_command).
- **After the merge:** `git fetch origin && git merge --ff-only origin/main` on local main, then `git rev-list --left-right --count origin/main...HEAD` should print `0	0`, and `mise bootstrap repos status` should say `current` for dev-profile.
