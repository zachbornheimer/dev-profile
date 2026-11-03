---
name: updating-oh-my-pi
description: Use for anything about omp itself — landing a branch into the custom omp build (fork zachbornheimer/oh-my-pi), adding or removing a branch from that build, fixing a failed omp-build run or conflict issue, installing, updating, verifying or rolling back omp via mise on the Mac and the fleet, making an upstream PR to can1357/oh-my-pi, or when the user wants personal omp behavior (a slash command, a transcript hide, a presentation toggle, a session hook, "an omp command" such as /thinking or /calm) or is about to edit oh-my-pi, packages/coding-agent or packages/tui for something they want for themselves. Personal omp behavior is an extension in ~/.config/omp/, listed in ~/.omp/agent/config.yml; do not modify the omp repo for that. Not for a Pi extension.
user-invokable: true
---

# oh-my-pi: extensions, landing branches, install

The `omp` you run is **the pinned upstream base + an ordered list of topic branches**, assembled and built once in GitHub Actions on the fork `zachbornheimer/oh-my-pi`, published as a release, and installed on every machine by mise. The base is **pinned** (`.github/omp-upstream.txt` on `ci`), not upstream main HEAD: upstream moves roughly hourly, and the pin is bumped deliberately every few days (§3), never chased per run.

- Checkout: `~/Developer/Personal/oh-my-pi`. Remotes: **`origin`** = upstream `can1357/oh-my-pi`, **`fork`** = `zachbornheimer/oh-my-pi`.
- **`main` is a read-only upstream mirror.** Never commit, merge or push to it. A GitHub ruleset, the local reference-transaction hook (installed by `bin/dev-profile-omp-machine-setup`) and `pretooluse-omp-main-branch-guard` all refuse it. Do not bypass them.
- **The branch list** is `.github/omp-rebuild.toml` (`branches = [ ... ]`, merged in order) on the fork's default branch **`ci`**, which holds only that file, `.github/omp-upstream.txt` (the pinned base), `.github/workflows/omp-build.yml` and `scripts/omp-build/resolve-branches.ts`.
- **CI** (`omp-build`, daily 04:00 UTC + manual dispatch) merges each listed branch with `git merge --no-ff` onto **the pinned base**, builds darwin-arm64 + linux-x64, and publishes release `build-<YYYYMMDD>-<upstream7>-<build7>` as Latest, `<upstream7>` being the pin. A scheduled run fails only on a conflict with the pinned base — never merely because upstream moved. A `workflow_dispatch` input `upstream_base` assembles a candidate base without committing it.

Design and history: [references/build-distribution.md](references/build-distribution.md).

## First: is this personal behavior or a change to omp itself?

**Personal behavior is an extension in `~/.config/omp/`.** The omp repo is not the place for a command or a hide the user wants for themselves. If the user explicitly says to change omp itself, or names an omp bug in the product, edit the repo and land it like any other branch (§2). Otherwise stop and write an extension (§1).

The failure this prevents: `/thinking` and `/calm` were patched into oh-my-pi. The user wanted `~/.config/omp/`. The installed omp never saw the commands, and the patch folded open tool rows because one apply path did two jobs.

## 1. A personal extension

1. `~/.config/omp/<name>/index.ts` — default export `function (pi: ExtensionAPI)`. Keep the pure rule in a sibling file with a `bun` test next to it.
2. List the directory in `~/.omp/agent/config.yml`:

   ```yaml
   extensions:
     - ~/.config/omp/<name>
   ```

   A directory that is not listed does not load; `~/.config/omp/` is not scanned. Restart omp — the running process will not see the command.
3. Draw and input only: not the message, the model context, or the export. Wrap `AssistantMessageComponent.prototype.updateContent` once for display, keep the raw message, and redraw already-drawn rows only on the user's toggle.
4. Prove it with `bun test` on the pure file, and confirm the omp repo diff does not contain the feature.

Detail, seams and the two working extensions to copy: [references/extensions.md](references/extensions.md) and [references/omp-seams.md](references/omp-seams.md). Read them before writing; do not re-derive the seams from the omp repo.

`~/.omp/agent/extensions/*.ts` (learn-command, undo-clear) is a different pile. New personal extensions go in `~/.config/omp/` and get listed.

## 2. Land a branch in the custom omp (in order)

1. **Branch off upstream in a worktree**, never off `main`:

   ```bash
   git -C ~/Developer/Personal/oh-my-pi fetch origin main
   wt -C ~/Developer/Personal/oh-my-pi switch --create feat/<slug> --base origin/main
   ```

2. **Build the change.** Format with `bunx oxfmt` (`useTabs: true` per `.oxfmtrc.json`; never `dprint` on oh-my-pi `.ts`). Run `bun check` and the targeted `bun test` files. Commit with `wt step commit`.
3. **Push the branch to the fork:** `git push -u fork feat/<slug>`.
4. **Probe the assembly exactly as CI will** (must exit 0):

   ```bash
   ~/.agents/skills/updating-oh-my-pi/scripts/probe-build.sh --add feat/<slug>
   ```

   It fetches `origin/main`, `fork/ci` and every listed branch, then merges them in order with `git merge-tree` onto **the pinned base** (no branch is changed; `origin/main` only when the pin file is absent). `--base <ref>` probes a different base (§3). `CONFLICT ... with the upstream base`: merge the base commit into your branch, resolve, push. `CONFLICT ... with an earlier branch in the list`: merge that branch into yours (or yours into it) and resolve once, so the later entry in the list already contains the resolution. **Merge, never rebase or force-push** a branch that is pushed or listed.
5. **Add the branch to the list on `ci`:**

   ```bash
   git -C ~/Developer/Personal/oh-my-pi fetch fork ci
   wt -C ~/Developer/Personal/oh-my-pi switch ci   # first time: switch --create ci --base fork/ci
   git pull --ff-only fork ci
   # edit .github/omp-rebuild.toml: append "feat/<slug>" after any branch it depends on
   wt step commit && git push fork ci
   ```

   If your branch contains another listed branch (`git merge-base --is-ancestor fork/<old> fork/feat/<slug>`), replace that entry instead of appending. Re-run the probe with no flags: it reads the pushed list.
6. **Build now** instead of waiting for 04:00 UTC, and watch the exact run id:

   ```bash
   gh workflow run omp-build.yml --repo zachbornheimer/oh-my-pi --ref ci
   gh run list --repo zachbornheimer/oh-my-pi --workflow omp-build.yml --limit 1 --json databaseId --jq '.[0].databaseId'
   gh run watch <that-id> --repo zachbornheimer/oh-my-pi --exit-status
   ```

   Copy the id: a mistyped id makes `gh run watch` return at once and look like success. A cold build (upstream touched Rust) takes about 23 min, warm about 4 min, and an unchanged tree skips the build after about 1 min.
7. **Install and prove the branch is in the binary** on each machine (the daily jobs do this at 05:00 local; do not wait):

   ```bash
   mise up github:zachbornheimer/oh-my-pi
   mise latest github:zachbornheimer/oh-my-pi        # the new tag
   rg -a -c -F '<string only your branch adds>' "$(mise which omp)"   # > 0
   ```

   `omp --version` is NOT proof: an upstream-only build prints the same version. Fleet: the same three lines over `ssh backend.ai`.

Never use `branches_override` to land anything. A dispatch with a non-empty override publishes a **prerelease**, which mise never installs; it is for experiments only.

## 3. Bump the pinned upstream base

**Bumping is deliberate: every few days, after a clean local check. Never a per-run chase.** Upstream main moves roughly hourly; assembling onto its HEAD means an upstream merge before every run. The pin decouples what we assemble from where upstream is.

1. **Pick the candidate: the newest upstream commit every listed branch already contains.** For each branch in `.github/omp-rebuild.toml`, take its most recent merge commit's second parent and verify it:

   ```bash
   m=$(git rev-list --merges -1 fork/<branch>)          # its most recent merge
   git rev-parse "$m^2"                                 # the upstream commit that merge brought in
   git merge-base --is-ancestor "$m^2" fork/<branch>   # and it is an ancestor of the branch
   ```

   Choose the **oldest** of those candidates: every branch already contains it, so each merges onto it without upstream conflicts. The candidate must also be on upstream: `git merge-base --is-ancestor <sha> origin/main`.
2. **Prove it locally** — must print `assembly clean`:

   ```bash
   ~/.agents/skills/updating-oh-my-pi/scripts/probe-build.sh --base <sha>
   ```

   A conflict here means the branch fights an **earlier branch in the list**, not the base: resolve once as in §2 step 4. To test a candidate in CI without committing it, dispatch `omp-build.yml` with input `upstream_base=<sha>`.
3. **Commit the pin** on `ci` — replace only the SHA line in `.github/omp-upstream.txt` — push, dispatch (§2 step 6). The new release's `<upstream7>` is the pin; `<build7>` differs from it because the branches are merged on top.

A probe with no flags reads this same pin, so it answers "will the next scheduled run assemble" — never "has upstream moved".

## 4. When a run fails

| Run error                                                                                                                  | Cause                                                                                                     | Fix                                                                                                             |
| -------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| `Conflict: omp-build: <branch> conflicts with the pinned upstream base (<sha>)` (one issue per branch, updated on repeats) | That branch conflicts with the pinned base (`.github/omp-upstream.txt`) or with a branch merged before it | Run the probe to see which; fix as in §2 step 4; push; re-dispatch; close the issue                             |
| `Missing branch`                                                                                                           | A listed branch is not on the fork                                                                        | Push it, or remove it from the list                                                                             |
| `Branchless assembly`                                                                                                      | The assembled SHA equals the pinned base (empty list)                                                     | Restore the list; CI refuses to publish the bare pin                                                            |
| `Bad upstream base`                                                                                                        | `.github/omp-upstream.txt`, or a dispatch `upstream_base` input, is not a full 40-hex SHA                 | Fix the pin on `ci`, or dispatch with a full SHA; see §3                                                        |
| Build or publish job failed                                                                                                | Compile or test error on the assembled tree                                                               | Merge the listed branches into a scratch worktree off the pinned base, run `bun check`, fix on the branch, push |

A failed run publishes nothing, so the previous release stays Latest and every machine keeps working.

## 5. Remove a branch

When upstream has merged a branch, `git cherry origin/main fork/feat/<slug>` prints only `-` lines. Delete it from `.github/omp-rebuild.toml` on `ci` (step 5), run the probe, push, dispatch (step 6).

## 6. Install facts

- mise tool (global `~/.config/mise/config.toml`, seeded from dev-profile `config/mise.toml`): `"github:zachbornheimer/oh-my-pi" = { version = "latest", matching = "omp-", minimum_release_age = "0" }`. `minimum_release_age = "0"` because the fork's own CI builds each release; the 24h default would hide every daily build.
- Stable entrypoint `~/.local/bin/omp` is a symlink to the mise shim, created by `bin/dev-profile-omp-machine-setup` (`mise run setup`). The capability gateway runs plain `omp` with only `~/.local/bin` on PATH: never delete it. Check with `env -i HOME="$HOME" PATH="$HOME/.local/bin:/usr/bin:/bin" ~/.local/bin/omp --version`.
- Daily update: macOS launchd agent `dev.mise.omp-daily-sync`, Linux systemd user timer `omp-daily-sync.timer`; both run `mise up github:zachbornheimer/oh-my-pi`.

## 7. Upstream pull requests

PRs to `can1357/oh-my-pi` come off a branch based on `origin/main`, never off another topic branch and never off `fork/main`. Read `CONTRIBUTING.md` and `.github/PULL_REQUEST_TEMPLATE.md` in the checkout first, keep the contributor's own sentence explaining the change, and get confirmation before posting any comment. A branch upstream accepts drops off the branch list (§5).

## 8. Roll back one machine

Pin a known-good tag in the machine-local `~/.config/mise/config.local.toml` (not synced), then `mise install`:

```toml
# ROLLBACK <date>: <why>. Remove once a fixed release is Latest.
[tools]
"github:zachbornheimer/oh-my-pi" = "build-<YYYYMMDD>-<upstream7>-<build7>"
```

Delete the block and run `mise up github:zachbornheimer/oh-my-pi` to return to Latest. Check `gh release list --repo zachbornheimer/oh-my-pi` for tags; never pin a prerelease.
