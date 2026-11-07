---
name: omp-build-assembly-conflicts
description: Unblock a failing omp-build assembly (branch conflicts) and force mise to see a new fork build on macOS.
---

Load when a `zachbornheimer/oh-my-pi` omp-build run fails with `CONFLICT <branch> conflicts with an earlier branch in the list`, or when `mise up github:zachbornheimer/oh-my-pi` says "up to date" but GitHub shows a newer build as Latest.

## mise will not see a new build (macOS)

mise caches the GitHub latest-release response under **`~/Library/Caches/mise/github`**, not `~/.cache/mise/github`. A stale `*-oh-my-pi-latest-*.msgpack.z` there makes `mise up` and `mise latest` report the old build while the new one is already Latest.

```bash
gh release list --repo zachbornheimer/oh-my-pi --limit 1        # what Latest actually is
rm -f ~/Library/Caches/mise/github/*oh-my-pi-latest-*.msgpack.z
mise up github:zachbornheimer/oh-my-pi
env -i HOME="$HOME" PATH="$HOME/.local/bin:/usr/bin:/bin" ~/.local/bin/omp --version   # second line names the release
```

`dev-profile-omp-sync` (dev-profile `bin/`) now clears both cache roots. Prove it bites with `bash -x …/dev-profile-omp-sync 2>&1 | rg 'rm -f'` — the line must name the `Library/Caches` path.

## A branch conflicts with an earlier branch in the manifest

The manifest merges branches in `layer` order onto fork `main`, so a later branch must already contain every earlier one. Resolve once, in a scratch worktree, on the failing branch:

1. Scratch worktree on the pushed branch: `git reset --hard -q <remote>/<branch>`, then `git merge --no-edit <the accumulated earlier branch>` (the branch directly before it in the list — it already contains the rest).
2. Resolve conflicts:
   - Default to **the accumulated side** (`git show ":3:<path>"`) for shared plumbing (`sdk.ts`, `session/agent-session.ts`, `irc/bus.ts`, task plumbing). Then run `bunx tsc --noEmit -p packages` inside `packages/coding-agent` and re-add the failing branch's own feature bits guided by the errors (often one missing import from its `settings.ts`).
   - Take **your side** (`":2:"`) only for files carrying the branch's own feature — check first: `git show ":2:$f" | rg -c '<featureSymbol>'` vs the same on `":3:"`.
   - A file present in the index but **not at stage 3** means the accumulated side deleted it on purpose; `git rm` it instead of resurrecting it.
3. Commit, push the branch (never force), re-run `~/.agents/skills/updating-oh-my-pi/scripts/probe-build.sh` until it prints `assembly clean: N branches`.
4. Dispatch (`gh workflow run omp-build.yml --repo zachbornheimer/oh-my-pi --ref main`), copy the returned run id, `gh run watch <id> --exit-status`.

## Facts that save time

- `~/Developer/Personal/oh-my-pi` has remotes `origin` (zachbornheimer) and `upstream` (can1357) and **no `fork`** — `probe-build.sh` fails there with "Please make sure you have the correct access rights". Run it from a worktree under `~/Developer/Personal/.worktrees/`, which has `fork`.
- The build job runs `bun install --frozen-lockfile`, `bun scripts/bazel-natives.ts host`, and `bun --cwd=packages/coding-agent run build` — **not** `bun test`. A red test on a listed branch does not block the release; only conflicts and compile errors do.
- `wt step commit` stages everything in the worktree, including untracked files carried from the main checkout (e.g. `agents/managed-skills/`). `git restore --staged <dir>` before committing when those are not part of the change, and re-check the mode with `git ls-files -s <path>` — a rewritten script can lose its executable bit.
