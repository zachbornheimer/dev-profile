---
name: sync-diverged-local-repos-and-lint-clean-push
description: "Bring a dirty, diverged local repo up to date with origin on a protected main (commit on a branch, merge origin, resolve conflicts, clear pre-push shellcheck/gitleaks without suppressions, PR)"
---

# Sync a dirty, diverged local repo with origin

Use when `mise bootstrap repos apply` refuses ("has local changes") or a repo is ahead/behind origin/main.

1. Inspect: `git fetch`, `git rev-list --left-right --count HEAD...@{u}`, `git status --short`. Do not touch dirty files you did not write until you know what they are.
2. Never commit on main (protected). `git switch -c <branch>`, commit by path groups with `git commit -m ... -- <paths>`. Pre-commit hooks (hk) may reformat; if files stay modified afterward, commit them as a `style:` commit.
3. Prefer `git merge --no-commit --no-ff origin/main` over `git rebase` when many local commits exist: rebase replays each commit and re-hits the same conflict; a merge shows the real count once.
4. Resolve conflict hunks: check what each side changed vs the merge base (`git diff <base> origin/main -- file`). If local extracted a script, port upstream edits into the extracted file and keep the local side. Keep the combined test assertions.
5. Merges and old commits can drop executable bits. Check `git diff origin/main HEAD --summary | grep 'mode change'` and `chmod` back.
6. Pre-push hooks lint the whole unpushed range. Fix findings by rewriting the construct into the plain form the tool understands (shebang instead of `# shellcheck shell=` directive, quote a subcommand named like a keyword, `export` stub variables, route a secret-named env read through one helper or destructure it). Do not call a scanner finding a false positive or add disable directives. Findings in already-merged commits can only go in `.gitleaksignore` (history-only, say so in the comment).
7. Run the repo's own tests for touched areas, `shellcheck`, and `gitleaks dir <path>` on the current tree.
8. Push the branch, open a PR with `gh pr create`; if checks are pending use `gh pr merge N --merge --auto`. Once merged, `git switch main && git merge --ff-only origin/main`, then `mise bootstrap repos status` should say `current`.
