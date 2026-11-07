---
name: omp-fork-push-hook-remotes
description: Pushing to zachbornheimer/oh-my-pi fails on foxguard because the clone has no origin remote
---

# Pushing to the oh-my-pi fork

## Symptom

`git push fork <branch>` from any `oh-my-pi` worktree fails after the code checks:

```text
foxguard-typescript – dev-profile-foxguard-introduced: target origin/main is not a commit here
✗ foxguard-typescript
error: failed to push some refs to 'https://github.com/zachbornheimer/oh-my-pi.git'
```

The commit itself succeeds; only the push is refused.

## Cause

`~/Developer/Personal/oh-my-pi` is cloned with two remotes, `fork`
(zachbornheimer/oh-my-pi) and `upstream` (can1357/oh-my-pi). There is no `origin`.
The `foxguard-typescript` pre-push hook from dev-profile diffs the pushed files
against `origin/main`, so it fails closed on every push.

## Fix

Add the missing remote once per clone (this is not a code problem, so do not
reach for `--no-verify`, which would also skip gitleaks and the format gates):

```sh
git remote add origin https://github.com/zachbornheimer/oh-my-pi.git
git fetch origin main:refs/remotes/origin/main
git push fork <branch>
```

`origin` must be the fork, not `upstream`: the hook means "the main this branch
lands on".

## Related

`git commit` in a worktree can fail with

```text
error: Unable to create '.../.git/packed-refs.lock': File exists
```

when several agents work in the same clone at once. Re-run the commit; check
`log -1` before re-committing, since the commit often did land.
