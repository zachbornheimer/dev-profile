---
name: worktrunk-index
description: Map raw git commands (add, commit, checkout -b, switch, merge, rebase, worktree add/remove, branch -d) to their Worktrunk `wt` equivalents with exact flags. Use when a hook denies raw git or when you need to branch, commit, merge, or clean up a worktree.
---

# Worktrunk index

Raw lifecycle git is denied by `~/.agents/hooks/worktree-lifecycle-guard.py` (rules: `hooks/lib/worktree_lifecycle_rules.py`). Use `wt`. Full table with flags: `references/commands.md`.

| Instead of | Run |
|---|---|
| `git add` + `git commit` | `wt step commit` |
| `git commit -a` | `wt step commit --stage tracked` |
| `git checkout -b X` / `git switch -c X` / `git worktree add` | `wt switch --create X [--base REF]` |
| `git checkout X` / `git switch X` | `wt switch X` |
| `git merge X` (into default) | `wt merge [TARGET]` |
| `git rebase main` | `wt step rebase [TARGET]` |
| `git worktree remove` / `git branch -d` | `wt remove [BRANCH]` (`-D` unmerged, `-f` dirty) |
| `gh pr checkout N` | `wt switch pr:N` |

Still plain git (no `wt` equivalent): first publish `git push -u`; post-rebase `git push --force-with-lease -u origin <branch>`; fetch, pull, stash, `commit --amend`, read-only commands. Existing-upstream fast-forward: `wt sync --push-only`.
