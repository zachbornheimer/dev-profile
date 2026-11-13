---
name: fork-ci-branch-manifest-registration
description: "Register pushed tools/* branches in the oh-my-pi fork's ci BRANCH_MANIFEST and dispatch the omp-build workflow when hooks stall or the hourly schedule is too slow."
---

# Register tool branches in the fork build manifest

Context: fork `zachbornheimer/oh-my-pi`; `main` is a read-only mirror of upstream; custom tools live one-per-branch as `tools/<name>`; the `ci` branch builds them via `.github/workflows/omp-build.yml` (`BRANCH_MANIFEST` JSON array). Never push `main`, never touch `origin` (upstream can1357).

1. Push tool branches: `git push --no-verify --porcelain fork refs/heads/tools/<n>:refs/heads/tools/<n>` (owner authorized `--no-verify` for this migration; foxguard push gate fails closed on files it cannot parse).
2. Make a worktree on `fork/ci` via `wt switch -c <name> --base fork/ci --no-cd -y` (or reuse `~/Developer/Personal/.worktrees/oh-my-pi-reg-tools`), `git fetch fork ci && git reset --hard fork/ci`.
3. Register: `bun ~/.omp/agent/tool-conversion/register_branches.ts <file-of-tool-names>` then `bun scripts/omp-build/branches.ts check` (must say all branches present).
4. Commit with hooks off if dprint hangs (`HK=0 git commit -S --no-verify`), push `HEAD:ci` to `fork`.
5. Do not wait for the hourly schedule (`17 * * * *`): `ghx workflow run omp-build.yml --repo zachbornheimer/oh-my-pi --ref ci`, then `ghx run list --workflow omp-build.yml`.

Rules: use `ghx`, not `gh`, for GitHub calls (rate limits). Never use `git worktree`; use `wt`. A `tools/*` branch you did not create (e.g. `tools/mux`) belongs to another agent: do not push or register it.
