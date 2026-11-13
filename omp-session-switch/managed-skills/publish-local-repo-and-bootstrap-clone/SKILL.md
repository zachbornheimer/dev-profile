---
name: publish-local-repo-and-bootstrap-clone
description: "Publish a local-only git repo to a private GitHub repo on this machine (protected main, hk hooks) and make mise bootstrap clone it on a new Mac via [bootstrap.repos]."
---

# Publish a local repo and have mise bootstrap clone it

1. In the repo: commit the dirty tree (conventional, signed `-S`). Pre-commit hk runs ruff etc.; fix the cause, never bypass. `git status` must end clean (delete stray `.bak-*` files via trash).
2. `gh repo create zachbornheimer/<name> --private --source=. --remote=origin --push`. The first push to `main` is refused by a guard; the override for the initial push only is `DEV_PROFILE_ALLOW_DEFAULT_BRANCH_PUSH=1 git push -u origin main`.
3. Pre-push hk re-runs lint on the whole repo (e.g. ruff EXE001 shebang needs `chmod +x`, PLW1510 needs `check=False`). Edits cannot be made in the main checkout (edit tool refuses): `wt switch -c fix/<slug> --no-cd`, edit in `~/Developer/Personal/.worktrees/<repo>-<slug>/`, commit there, `wt merge -y main`, then push with the override from the main checkout. Do not stage changes in main first (a failed commit leaves them staged; `git reset -q && git checkout -q <file>`).
4. In dev-env (`~/Developer/Personal/dev-env`), do the same worktree flow and add to `mise.macos.toml`:
```toml
[bootstrap.repos."~/Developer/Personal/<name>"]
url = "https://github.com/zachbornheimer/<name>.git"
ref = "main"
```
5. Verify with `MISE_ENV=macos mise bootstrap repos status` (expect `current`). `repos apply` fails on a dirty checkout, so keep the clone clean. Run from the main checkout with `MISE_ENV=macos`; a worktree needs `mise trust .` first.
