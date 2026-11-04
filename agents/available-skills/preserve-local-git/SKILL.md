---
name: preserve-local-git
description: Push unique local Git work to origin before deleting a clone, switching machines, or handing off a repo. Use when the user says /preserve-local-git, "preserve this clone", "what would I lose if I delete this folder", "push unique local work", "convert stashes to branches", or "I'm moving this repo to another computer."
---

# Preserve local Git

Get every unique local commit, dirty tree, and stash onto `origin` so another clone can continue. Do not delete the folder. Do not run `zq prune --apply`.

Pair with `cleaning-git-branches-and-worktrees` only after origin holds the unique tips.

## Gotchas

- Never commit on a dirty shared main checkout. Snapshot onto a new worktree.
- `wt switch` background is the default; always `--no-cd --no-hooks --yes`.
- Never push a machine-local `replace` / path (`../.worktrees/...`, `/Users/...`).
- Never `git stash branch` (it drops the stash). Never `git checkout stash^2 -- .` (misses the WIP tree or fails).
- Never drop a local stash until `origin` contains the converted SHA.
- Never force-push `main` or an existing unique feature branch. `--force-with-lease` is allowed only on `backup/stash-*` you just created this run.
- `unsure` means keep the local copy and still push a backup.

## Safety

1. Never discard uncommitted or untracked unique work.
2. Snapshot dirty trees with `wt`; leave the original dirty tree untouched until origin has the SHA.
3. Skip logs, build binaries, and lockfiles the default branch does not track.

## Workflow

### 1. Fetch

```bash
git fetch --prune
```

Work from a linked worktree, not a dirty shared main.

### 2. Push unique branch tips

For each local branch other than `main` / the default:

- If `origin/<branch>` already has this SHA, skip.
- If origin lacks the SHA, `git push -u origin <sha>:refs/heads/<branch>` (no force).
- If the names diverged, push `backup/<branch>` instead of overwriting origin.

Skip fixture branches (`feature/fixture-*`).

### 3. Snapshot dirty trees

Per dirty worktree (including main), from the repo:

```bash
wt switch --create wip/<slug> --base <sha-or-branch> --no-cd --no-hooks --yes
```

`--base` is any commit-ish (SHA or branch). Config path: `{{ repo_path }}/../.worktrees/{{ repo }}-{{ branch | sanitize }}`.

Then:

1. Copy `git -C <dirty> diff` and unique untracked source onto that worktree.
2. Strip machine-local `replace` lines from `go.mod` / lockfiles before commit.
3. `wt step commit`.
4. `git push -u origin <sha>:refs/heads/wip/<slug>` (no force).
5. Leave the original dirty tree untouched until origin has the SHA.

If `wt` is missing, print the commands for the user. Do not run `git worktree add`.

### 4. Convert stashes (this is the transfer format)

Stashes do not travel. Convert each:

```bash
wt switch --create backup/stash-<slug> --base 'stash@{N}^1' --no-cd --no-hooks --yes
git stash show -p --binary --include-untracked stash@{N} | git -C <path> apply --index --3way
# strip machine-local replace; unstage logs/binaries
wt -C <path> step commit
git push -u origin backup/stash-<slug>
```

`<path>` is the worktree from `wt switch` (`{{ repo_path }}/../.worktrees/{{ repo }}-{{ branch | sanitize }}`). Quote `stash@{N}^1`. If `wt` is missing, print these commands. Do not run `git worktree add`.

Keep the local stash until `git fetch` shows that SHA on origin.

Restore on the other machine:

```bash
git fetch origin
wt switch backup/stash-<slug>
```

### 5. Linked repos

If a dirty `replace` or submodule points at another local checkout, run this skill there too. A SHA that exists only as detached HEAD on that checkout is unique.

### 6. Report

List:

- branches pushed (name + SHA)
- dirty snapshots (`wip/*` SHA)
- stash backups (`backup/stash-*` SHA)
- skipped junk
- anything still only local

End with the clone command for the other computer: `git clone`, then `wt switch <wip-or-backup-branch>` when `wt` is present.

Scope measurement: a comment-only change to exercise the per-file steps.
