# Worktrunk command index

Every flag below was checked against `wt <cmd> --help` on this machine (2026-10-07). The worktrunk.dev pages were not fetched (WebFetch unavailable to the worker); `--help` output is the source.

Global flags on every command: `-C <path>`, `--config <path>`, `--config-set <toml>`, `-v`, `-y/--yes`.

## git -> wt

| Raw git | wt | Flags (verified) |
|---|---|---|
| `git add` / `git stage` + `git commit` | `wt step commit` | `-b/--branch <B>`, `--stage all\|tracked\|none` (default all), `--dry-run`, `--no-hooks`, `--format text\|json` |
| `git commit -a` | `wt step commit --stage tracked` | same |
| commit already-staged index | `wt step commit --stage none` | same |
| `git checkout -b X`, `git switch -c X`, `git branch X`, `git worktree add` | `wt switch --create X` | `-c/--create`, `-b/--base <B>` (supports `^ @ - pr:N mr:N`), `-x/--execute <PROG> [-- args]`, `--clobber`, `--no-cd` |
| `git checkout X`, `git switch X` | `wt switch X` | shortcuts `^` default branch, `-` previous, `@` current, `pr:N`, `mr:N`; no branch opens a picker |
| `gh pr checkout N` | `wt switch pr:N` | |
| `git merge X` | `wt merge [TARGET]` | `--no-squash`, `--no-commit`, `--no-rebase`, `--no-remove`, `--no-ff`, `--stage all\|tracked\|none`, `--no-hooks`, `--format` |
| squash branch commits | `wt step squash [TARGET]` | `--stage`, `--dry-run`, `--no-hooks` |
| `git rebase TARGET` | `wt step rebase [TARGET]` | `--format` |
| fast-forward target to branch (local) | `wt step push [TARGET]` | `--no-ff`, `--format` (local only, not a remote push) |
| `git rebase --onto` / stacked branches | `wt sync` | `-s/--stack`, `-a/--all`, `-f/--fetch`, `-p/--push`, `--push-only`, `-P/--prune`, `-F/--force`, `-n/--dry-run`, `-v` |
| `git worktree remove`, `git branch -d/-D` | `wt remove [BRANCHES...]` | `--no-delete-branch`, `-D/--force-delete`, `-f/--force`, `--foreground`, `--reap`, `--no-hooks`, `--format` |
| `git worktree prune` | `wt step prune` | `--dry-run`, `--min-age <AGE>` (default 1d), `--foreground`, `--format` |
| `git worktree move` | `wt step relocate` | experimental |
| `git diff <default>...HEAD` plus untracked | `wt step diff [TARGET] [-- git-diff-args]` | |
| `git worktree list` | `wt list` | `--format table\|json`, `--branches`, `--remotes`, `--full`, `--progressive` |

## Other wt commands

- `wt step copy-ignored`, `wt step eval`, `wt step for-each -- <cmd>`, `wt step promote [BRANCH]` (experimental), `wt step tether` (experimental).
- `wt hook show|pre-switch|post-switch|pre-start|post-start|pre-commit|post-commit|pre-merge|post-merge ...`
- `wt config shell|create|show|update|approvals|alias|plugins`

## Machine specifics

- `wt sync` is the `wt-sync` plugin (rebases stacked worktree branches in dependency order).
- `workz` is a separate tool: dependency/env sync for agent worktrees (`workz start|list|switch|done|sync|status|clean|conflicts|doctor|hook|mcp|init`). `wt` post-start hooks call it; prefer `wt` for lifecycle.
- Worktree path template (`~/.config/worktrunk/config.toml`): `{{ repo_path }}/../.worktrees/{{ repo }}-{{ branch | sanitize }}`.
- Commit messages come from `[commit.generation]` (`_llm`, Conventional Commits).

## Not covered by wt (stays plain git)

First publish: `git push -u`. Existing-upstream fast-forward: `wt sync --push-only`. Post-rebase: `git push --force-with-lease -u origin <branch>`. Also stays plain git: `fetch`, `pull`, `stash`, `commit --amend`, `restore`, and read-only commands (`status`, `diff`, `log`, `show`, `blame`, `rev-parse`, `branch --list`).
