---
name: rename-git-remotes
description: "Rename a checkout's git remotes when the names collide on shared refs, such as swapping origin and fork to the upstream/origin convention. Use when a git remote rename fails with \"reference already exists\" or leaves a stale packed-refs.lock."
---

# Rename git remotes when refs collide

`git remote rename A B` fails with `cannot lock ref 'refs/remotes/B/<name>': reference already exists` when both remotes have fetched the same branch name. It can also leave the rename half-done: the remote config moved, but the refs did not.

## Fix

1. Check state first: `git remote -v` and `git config --get-regexp '^remote\.'`. Note which remote's fetch refspec still points at the old ref namespace.
2. Point the renamed remote's refspec at its own namespace:
   `git config remote.<new>.fetch '+refs/heads/*:refs/remotes/<new>/*'`
3. Move the refs, then delete the old ones:
   ```sh
   git for-each-ref refs/remotes/<old> | while read sha type ref; do
     git update-ref "refs/remotes/<new>/${ref#refs/remotes/<old>/}" "$sha" \
       && git update-ref -d "$ref"
   done
   ```
   This is slow (one ref at a time, hundreds of refs). Let it finish; do not kill it.
4. If a step reports `packed-refs.lock: File exists`, check for a holder with `lsof .git/packed-refs.lock`. Only delete the lock when no process holds it, then retry.
5. Remove any leftover remote that now duplicates another (`git remote remove <old>`), set `promisor` and `partialclonefilter` on the new remote if the old one had them, then `git fetch` both and confirm the tips: `git rev-parse --short refs/remotes/<name>/main`.

## Verify

- `git remote -v` shows only the intended names.
- `git for-each-ref refs/remotes/<old>` is empty.
- Each remote's `main` tip is the commit you expect, not the other remote's.

## Seen

oh-my-pi checkout, 2026-11-07: renaming `origin` (can1357) to `upstream` collided on branch `11868-followup`, which both remotes had fetched. The rename left `upstream` configured but its refs still under `refs/remotes/origin/`. A killed retry left a stale `packed-refs.lock` with no holder.
