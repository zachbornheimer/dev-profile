# Cleanup procedure

Use only after the audit has produced a settled delete set and the user requested cleanup.

Do not proceed when PR lookup is unavailable or another deletion-gate fact is unresolved.

## Preferred path: `wt`

Check capability first:

```bash
command -v wt
```

If `wt` is present:

1. Before removing anything, verify every named candidate still points at its reviewed SHA:

   ```bash
   test "$(git rev-parse --verify refs/heads/<branch>)" = "<reviewed-sha>"
   ```

   Any mismatch returns that candidate to triage. Do not re-review or re-remove it implicitly.

2. Preview integrated (`_` / `⊂`) candidates. Default `--min-age 1d`. Skips locked, dirty, and the main worktree.

   ```bash
   wt step prune --dry-run
   ```

   JSON `--dry-run` fields: `branch_deleted`, `reason`, `target`. Restrict the apply set to audit-settled integrated candidates. Drop any row that is keep / recover / unsure, SHA-mismatched, locked, or dirty.

3. Apply only after that filter:

   ```bash
   wt step prune --foreground --yes
   ```

   Always `--foreground` (background is the default). Do not use `wt merge`.
   This also drops stale registrations (except those with staged metadata).

4. Remove leftover worktrees the audit marked settled (not already taken by prune):

   ```bash
   wt remove --foreground --no-delete-branch --yes <branch>
   ```

   Detached: pass the path (`branch` is null). `--force` only after `preserve-local-git` covered that dirty tree. `-D` is for unmerged branches and is not this path.

5. Leftover settled branches (no remaining worktree):

   ```bash
   wt remove --foreground --yes <branch>
   ```

   Independently verified settled branches that need force: `wt remove --foreground -D --yes <branch>`; if the environment blocks forced deletion, print the exact commands rather than bypassing the guard.

If a branch or worktree changed after the dry-run, do not re-apply automatically. Return it to triage.

## Fallback when `wt` is missing

Use `zq prune mark` if `zq prune mark --help` succeeds; otherwise the bundled backup script.

### `zq prune mark`

1. SHA-check every candidate as above. Any mismatch returns it to triage.

2. Mark every still-valid settled branch:

   ```bash
   zq prune mark <branch> --reason "<classification/verdict: concise reason>"
   ```

3. Preview with `zq prune`. Verify marked count matches the delete set, no branch changed since marking, every dirty worktree that would be removed is backed up, and no unresolved or unverified-PR candidate is included.

4. Apply only after those checks: `zq prune --apply`. Capture the backup directory and restore command.

If a branch or worktree changed after marking, do not re-mark automatically. Return it to triage.

### Bundled backup script

Use when `zq prune mark` is also unavailable.

The fallback delete-set is branch-based. Do not remove detached worktrees through this path. Preserve their HEAD with a named ref/branch and account for any local edits first, then re-inventory.

Create a tab-separated delete set with these columns:

```text
branch sha why worktree dirty_files reason
```

Example:

```text
feature/old-search 0123456789abcdef0123456789abcdef01234567 superseded /Users/me/repo-search 0 behavior shipped in PR #418
```

The `sha` must be the exact branch tip reviewed during triage. `dirty_files` must be the known, non-negative worktree dirty-file count from that same inventory. Unknown worktree state is not eligible for cleanup.

Run:

```bash
python scripts/backup.py \
  --repo <repo> \
  --delete-set <delete-set.tsv> \
  --backup-dir <scratch>/repo-backup-<date>/
```

The script fails closed when:

- the delete-set schema or safety fields are invalid;
- a candidate branch moved or disappeared and no valid candidates remain;
- a recorded worktree HEAD no longer matches the reviewed branch SHA;
- a dirty worktree disappeared;
- its dirty-file count changed after triage;
- a dirty worktree expected to be backed up was not saved;
- bundle verification or bundle-head accounting fails.

The script never deletes refs or worktrees.

After it succeeds:

1. Read `delete-ok.tsv`; only those rows are eligible for removal.
2. Preferred path is `wt remove` / `wt step prune`. Do not run `git worktree remove`, `git worktree prune`, or `git branch -d`/`-D`.
3. Never use `rm -rf` or `git worktree remove --force` to bypass safety.
4. If `wt` is unavailable, print these git commands for the user (do not run them):
   - Remove clean or backed-up worktrees first: `git worktree remove <path>`
   - Delete merged/ancestry-safe settled branches: `git branch -d <branch>`
   - Independently verified settled branches that need force: `git branch -D`
   - Finish with `git worktree prune`.

## Recoverable work

A `unique` verdict does not imply that an old branch should be merged as-is.

Prefer reconstructing the needed change from the current default branch, using the old branch as evidence. Reuse or rebase the old branch only when it remains clean, understandable, and verifiable.

Keep the old branch until the replacement is safely preserved.
