---
name: updating-oh-my-pi
description: Use for anything about omp itself — landing a branch into the custom omp build (fork zachbornheimer/oh-my-pi), adding or removing a branch from that build, fixing a failed omp-build run or conflict issue, installing, updating, verifying or rolling back omp via mise on the Mac and the fleet, making an upstream PR to can1357/oh-my-pi, or when the user wants personal omp behavior (a slash command, a transcript hide, a presentation toggle, a session hook, "an omp command" such as /thinking or /calm) or is about to edit oh-my-pi, packages/coding-agent or packages/tui for something they want for themselves. Personal omp behavior is an extension in ~/.omp/agent/extensions/ (auto-discovered, no config entry); do not modify the omp repo for that. Not for a Pi extension. Not for a tool that agents call (a new tool for omp, a tool in the zab-ai package, a native omp tool, an MCP gateway tool): that is the creating-new-tools skill.
  user-invokable: true
---

# oh-my-pi: extensions, landing branches, install

The `omp` you run is **fork `main` (an exact upstream mirror) + an ordered list of topic branches**, assembled and built once in GitHub Actions on the fork `zachbornheimer/oh-my-pi`, published as a release, and installed on every machine by mise. The base is `main` itself, advanced only by `scripts/sync-fork-main.sh` (§3); there is no pin file.

- Checkout: `~/Developer/Personal/oh-my-pi`. Remotes: **`origin`** = upstream `can1357/oh-my-pi`, **`fork`** = `zachbornheimer/oh-my-pi`.
- **`main` is a read-only upstream mirror, and the assembly base.** Never commit, merge or push to it. A GitHub ruleset (`main-mirrors-upstream`: no update, no delete, no force-push, no bypass), the local reference-transaction hook (installed by `bin/dev-profile-omp-machine-setup`) and `pretooluse-omp-main-branch-guard` all refuse it. The only way it moves is `scripts/sync-fork-main.sh` (§3). Do not bypass the guards by hand.
- **The branch list** is the `BRANCH_MANIFEST` block in `.github/workflows/omp-build.yml` (a JSON array of `{ "branch": ..., "reason": ... }` entries, merged in order) on the fork's default branch **`ci`**, which holds only that workflow, `scripts/omp-build/resolve-branches.ts` (the single parser of the manifest) and a README. It carries no upstream source tree.
- **CI** (`omp-build`, hourly poll at minute 17 + manual dispatch; an unchanged tree skips in about a minute) merges each listed branch with `git merge --no-ff` onto **fork `main`**, builds darwin-arm64 + linux-x64, and publishes release `build-<YYYYMMDDHHMMSS>-<main7>-<build7>` as Latest, `<main7>` being the `main` commit it assembled onto. Assembly refuses a `main` that holds commits upstream lacks. Assembly computes the tag and bakes it into both binaries, so `omp --version` prints it on a second line as `github.com/zachbornheimer/oh-my-pi@<tag>`. A branch conflict leaves the previous release Latest. A dispatch with `branches_override` publishes a prerelease only.

Design and history: [references/build-distribution.md](references/build-distribution.md). Why the fork is shaped this way, and the chosen direction (carry on `main`, one manifest file per branch, fewer branches): the `forking-projects` skill. This skill stays the source for every live command.

## First: is this a tool agents call, personal behavior, or a change to omp itself?

**A tool that agents call is not an extension here.** "A new tool for omp", "add it to the zab-ai package", "expose it over MCP", and "make this a native omp tool" belong to the `creating-new-tools` skill (§0 and §4.1): the logic goes in `@zab-ai/ai`, with a Mastra mount and, if it must be native, an adapter in `mastra/adapters/omp/zab-ai-tools`. Use this skill for what the user triggers or sees (a command, a hide, a toggle, a hook), or for the omp build itself. A request can need both: build the tool there and its command here, and keep one copy of the logic.

**Personal behavior is an extension in `~/.omp/agent/extensions/`.** The omp repo is not the place for a command or a hide the user wants for themselves. If the user explicitly says to change omp itself, or names an omp bug in the product, edit the repo and land it like any other branch (§2). Otherwise stop and write an extension (§1).

The failure this prevents: `/thinking` and `/calm` were patched into oh-my-pi. The user wanted an extension. The installed omp never saw the commands, and the patch folded open tool rows because one apply path did two jobs.

## 1. A personal extension

1. `~/.omp/agent/extensions/<name>/index.ts` (or `<name>.ts`) — default export `function (pi: ExtensionAPI)`. Keep the pure rule in a sibling file with a `bun` test next to it.
2. omp auto-discovers `~/.omp/agent/extensions/` (modules one level deep; project-scoped: `<repo>/.omp/extensions/`). No `config.yml` entry is needed. Restart omp — the running process will not see the command. `extensions:` in `~/.omp/agent/config.yml` is only an optional way to load a path outside the native directories.
3. Draw and input only: not the message, the model context, or the export. Wrap `AssistantMessageComponent.prototype.updateContent` once for display, keep the raw message, and redraw already-drawn rows only on the user's toggle.
4. Prove it with `bun test` on the pure file, and confirm the omp repo diff does not contain the feature.

Detail, seams and the two working extensions to copy: [references/extensions.md](references/extensions.md) and [references/omp-seams.md](references/omp-seams.md). Read them before writing; do not re-derive the seams from the omp repo.

Agent-callable tools can also live in `~/.omp/agent/tools/`, but in this setup they are routed through the `creating-new-tools` skill, not written here.

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

   It fetches `origin/main`, `fork/main`, `fork/ci` and every listed branch, then merges them in order with `git merge-tree` onto **fork `main`** (no branch is changed). `--base <ref>` probes a different base. `CONFLICT ... with the upstream base`: merge `main` into your branch, resolve, push. `CONFLICT ... with an earlier branch in the list`: merge that branch into yours (or yours into it) and resolve once, so the later entry in the list already contains the resolution. **Merge, never rebase or force-push** a branch that is pushed or listed.
5. **Add the branch to the list on `ci`:**

   ```bash
   git -C ~/Developer/Personal/oh-my-pi fetch fork ci
   wt -C ~/Developer/Personal/oh-my-pi switch ci   # first time: switch --create ci --base fork/ci
   git pull --ff-only fork ci
   # edit the BRANCH_MANIFEST block in .github/workflows/omp-build.yml: append { "branch": "feat/<slug>", "reason": "..." } after any branch it depends on
   wt step commit && git push fork ci
   ```

   If your branch contains another listed branch (`git merge-base --is-ancestor fork/<old> fork/feat/<slug>`), replace that entry instead of appending. Re-run the probe with no flags: it reads the pushed list.
6. **Build now** instead of waiting for the next hourly poll, and watch the exact run id:

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

   `omp --version` names the installed release (`github.com/zachbornheimer/oh-my-pi@build-…` on its second line), which proves which build is on the machine but not that a specific branch is in it — grep a branch-only string for that. Fleet: the same three lines over `ssh backend.ai`.

Never use `branches_override` to land anything. A dispatch with a non-empty override publishes a **prerelease**, which mise never installs; it is for experiments only.

## 3. Sync fork main (take new upstream)

**The base is fork `main`. There is no pin file.** `main` is an exact fast-forward mirror of `can1357/oh-my-pi:main`, so advancing the base means syncing `main`, and nothing else moves it. A scheduled build uses whatever `main` is when it runs: a build never fails merely because upstream moved after the last sync, and it fails on a conflict only when `main` has been synced past what a topic branch contains.

1. **Sync `main`** (fast-forward only; backs up first; opens the ruleset's admin bypass for one API call and always closes it again):

   ```bash
   bash ~/.agents/skills/updating-oh-my-pi/scripts/sync-fork-main.sh
   ```

   It refuses when `main` is not a pure ancestor of upstream `main`. Never push to `main` by hand, never widen the ruleset's bypass list, and never leave a bypass open.
2. **Prove the branches still assemble** — must print `assembly clean`:

   ```bash
   bash ~/.agents/skills/updating-oh-my-pi/scripts/probe-build.sh
   ```

   The probe assembles onto fork `main` (the same base CI uses). `CONFLICT ... with the upstream base` means a branch fights the new `main`: merge `main` into that branch, resolve, push (§2 step 4). `CONFLICT ... with an earlier branch in the list` means two branches fight each other: resolve once as in §2 step 4.
3. **Dispatch** the build (§2 step 6).

**One change per branch, based on `main`, never stacked on another topic branch.** Stacks are how a dozen entries ended up conflicting with upstream on the same files at once, and a conflict in the bottom of a stack blocks every branch above it. When a branch contains another listed branch, list only the top one.

## 4. When a run fails

Match the run's error to its cause:

- `Conflict: omp-build: <branch> conflicts with upstream` (one issue per branch, updated on repeats): that branch conflicts with fork `main` or with a branch merged before it. Run the probe to see which; fix as in §2 step 4; push; re-dispatch; close the issue.
- `Missing branch`: a listed branch is not on the fork. Push it, or remove it from the list.
- `Branchless assembly`: the assembled SHA equals fork `main` (empty list). Restore the list; CI refuses to publish the bare mirror.
- `main is not a mirror`: fork `main` holds commits that upstream `main` lacks. Cherry-pick them onto a topic branch based on `main`, then restore `main` to a pure upstream ancestor (ruleset bypass by a repo admin, as `sync-fork-main.sh` does, then close it). `sync-fork-main.sh` refuses a diverged `main` and does not repair it.
- `Bad base`: the fork's `main` ref did not resolve to a commit SHA. Check `gh api repos/zachbornheimer/oh-my-pi/git/ref/heads/main`.
- Build or publish job failed: compile or test error on the assembled tree. Merge the listed branches into a scratch worktree off fork `main`, run `bun check`, fix on the branch, push.

A failed run publishes nothing, so the previous release stays Latest and every machine keeps working.

## 5. Remove a branch

When upstream has merged a branch, `git cherry origin/main fork/feat/<slug>` prints only `-` lines. Delete it from the `BRANCH_MANIFEST` block in `.github/workflows/omp-build.yml` on `ci` (step 5), run the probe, push, dispatch (step 6).

## 6. Install facts

- mise tool (global `~/.config/mise/config.toml`, seeded from dev-profile `config/mise.toml`): `"github:zachbornheimer/oh-my-pi" = { version = "latest", matching = "omp-", minimum_release_age = "0" }`. `minimum_release_age = "0"` because the fork's own CI builds each release; the 24h default would hide every daily build.
- Stable entrypoint `~/.local/bin/omp` is a symlink to the mise shim, created by `bin/dev-profile-omp-machine-setup` (`mise run setup`). The capability gateway runs plain `omp` with only `~/.local/bin` on PATH: never delete it. Check with `env -i HOME="$HOME" PATH="$HOME/.local/bin:/usr/bin:/bin" ~/.local/bin/omp --version`.
- Daily update: macOS launchd agent `dev.mise.omp-daily-sync`, Linux systemd user timer `omp-daily-sync.timer`; both run `~/.local/share/dev-profile/bin/dev-profile-omp-sync`, which drops mise's cached "latest release" response (a build published minutes ago is otherwise invisible), runs `mise up github:zachbornheimer/oh-my-pi`, and exits 1 unless `omp --version` names the version mise has active.

## 7. Upstream pull requests

PRs to `can1357/oh-my-pi` come off a branch based on `origin/main`, never off another topic branch and never off `fork/main`. Read `CONTRIBUTING.md` and `.github/PULL_REQUEST_TEMPLATE.md` in the checkout first, keep the contributor's own sentence explaining the change, and get confirmation before posting any comment. A branch upstream accepts drops off the branch list (§5).

## 8. Roll back one machine

Pin a known-good tag in the machine-local `~/.config/mise/config.local.toml` (not synced), then `mise install`:

```toml
# ROLLBACK <date>: <why>. Remove once a fixed release is Latest.
[tools]
"github:zachbornheimer/oh-my-pi" = "build-<YYYYMMDDHHMMSS>-<upstream7>-<build7>"
```

Delete the block and run `mise up github:zachbornheimer/oh-my-pi` to return to Latest. Check `gh release list --repo zachbornheimer/oh-my-pi` for tags; never pin a prerelease.
