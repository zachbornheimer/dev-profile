# Dev Profile

`profile.pkl` is the source of truth. hk, dprint, mise, Worktrunk, and Conform
configs are rendered from it into `~/.local/share/dev-profile`.

Fresh machine (after mise is installed):

```bash
mise bootstrap --from git@github.com:zachbornheimer/dev-profile.git
```

Bootstrap installs Pkl, renders the profile into `~/.local/share/dev-profile`,
backs up any live configs it would replace to `~/.local/state/dev-profile/backups`,
then re-runs `mise bootstrap` on the generated config. That second pass installs
the tools and links hk, dprint, Worktrunk, mise, and Conform configs.

Add one line to `~/.zshrc` for mise activation and `wt switch` cd support:

```bash
source ~/.local/share/dev-profile/shell.zsh
```

```bash
mise run diff-live   # what linking would change
mise run rollback    # restore the backed-up originals
```

## Layout

| Path                     | Role                                                        |
| ------------------------ | ----------------------------------------------------------- |
| `mise.toml`              | kernel: Pkl pin and tasks                                   |
| `profile.pkl`            | languages, runtime pins, live paths; derives the hooks      |
| `tools/<category>/`      | one file per tool: doc, pin, scripts, its step per hook     |
| `lib/Tool.pkl`           | the template every tool file amends                         |
| `lib/hk.pkl`             | the hk config, assembled from the tools                     |
| `lib/script.pkl`         | bash fragments the tool scripts share                       |
| `lib/render.pkl`         | one renderer per generated file                             |
| `lib/contract.pkl`       | the repo task contract (`mise run lint`, `test`, `scan`...) |
| `lib/pr.pkl`             | the `wt pr` family: publish, watch to merge                 |
| `lib/sync.pkl`           | `wt sync`, `reconcile`, `prune`, `tidy`: back up and clean  |
| `tests/profile.test.pkl` | invariants and a snapshot of what each hook runs            |
| `tests/*-fixture.sh`     | the generated scripts against real git and go               |
| `mise-tasks/bump`        | bump every outdated pin to its latest release               |
| `.github/workflows/`     | `ci` runs doctor on every push and PR; `bump` runs weekly   |

## What runs when

| Event                   | Files            | Mode                        | Steps                                                                                   |
| ----------------------- | ---------------- | --------------------------- | --------------------------------------------------------------------------------------- |
| save (Neovim)           | the buffer       | format                      | dprint, from the language's `dprint` binding                                            |
| `git commit`            | staged           | fix, restaged; checks block | every tool's `pre-commit` entry, dprint last                                            |
| `git push`              | the pushed range | check only                  | every tool's `pre-push` entry                                                           |
| `hk fix` / `hk check`   | modified         | fix / check                 | the `pre-commit` entries                                                                |
| `hk check --slow --all` | whole tree       | check                       | the `pre-commit` and `pre-push` entries                                                 |
| `mise run lint`         | whole tree       | check                       | `hk check --all --slow --profile lint` (commit guards off) plus the suppressions report |
| `mise run test`, `scan` | whole tree       | native tools                | the contract adapters in `lib/contract.pkl`, not hk                                     |
| `mise run ci`           | whole tree       | all of the above            | `lint`, then `test`, then `scan`                                                        |

A `fix` rewrites what it safely can and never blocks: push judges the rest. A
`check` may block. Per-file push checks run on the files changed since the
default branch; whole-program linters (golangci-lint, go vet, clippy) fail only
on issues new in that range, so old debt never blocks a push. Full-tree runs are
explicit, never in hooks. CI judges the full tree.

`mise run explain go` prints the resolved plan for one tool or one `tools/`
category: the step name per hook, its command, files and ordering.

## Pull requests from wt

`lib/pr.pkl` renders two scripts and the aliases that call them. None of
them prompt, so loops and scripts can drive them.

| Alias         | Does                                                                |
| ------------- | ------------------------------------------------------------------- |
| `wt pr [B]`   | commit pending work, push (never force), reuse or open a PR         |
| `wt pr-draft` | same, as a draft                                                    |
| `wt pr-auto`  | same, then watch CI, merge when green, notify, remove the worktree  |
| `wt ship`     | `pr-draft` for the current worktree; skips what has nothing to send |
| `wt ship-all` | `ship` in every worktree                                            |

`B` switches to that branch first; without it, the current branch is published.
`--create=<branch> -- <cmd>` makes a fresh branch, runs `<cmd>` in it, and
publishes what changed. A command that changes nothing removes its worktree:

```bash
# One auto-merging PR per repo that still has a Prettier config.
fd -H -E .worktrees -t f '^\.prettierrc' ~/Developer/Personal -x git -C {//} rev-parse --show-toplevel |
  sort -u |
  xargs -I{} wt -C {} pr-auto --create=chore/remove-prettier -- fd -H '^\.prettierrc' -X rm
```

`wt pr-auto` watches in a background kitty tab when run interactively in kitty
(the tab title shows progress and turns red or green; the notification focuses
it). From a loop or script it watches detached and logs to
`.git/wt/logs/pr-watch-<branch>.log`. `DEV_PROFILE_PR_WATCH=tab|background`
overrides the choice. The watcher merges only after every check passes, even
where the branch has no protection, using the repo's default merge method
(`DEV_PROFILE_PR_MERGE_METHOD` overrides). Where GitHub refuses auto-merge
(a private repo on the Free plan), `pr-auto` merges directly once checks pass.
After the merge it fast-forwards your local default branch where it is checked
out, so that checkout's `post-merge` hooks run. Here, `mise run install-git-hooks`
adds one: a pull or merge that moves `main` runs `mise run generate`, so the
live profile follows `main`.

## Backing up and tidying clones

`lib/sync.pkl` keeps every clone of a repo backed up to GitHub, so several
copies on one machine (or several machines) can converge and be cleaned up.

| Alias               | Does                                                                |
| ------------------- | ------------------------------------------------------------------- |
| `wt sync`           | push everything unique in this clone; touches no files              |
| `wt reconcile B`    | rebase `B` onto GitHub's copy; stops on a conflict for you          |
| `wt prune`          | remove worktrees and branches merged into `main`                    |
| `wt prune --pushed` | also clean worktrees and branches identical to GitHub's             |
| `wt prune --remote` | also delete GitHub branches already absorbed into `main`            |
| `wt tidy`           | `sync`, then `prune --remote --pushed`; stops if anything conflicts |

What `wt sync` sends, all under this clone's own `backup/<clone>/` namespace
unless it is a plain branch:

- **Branches:** pushed, never forced. If another clone moved the same branch
  on GitHub, this clone's commits are rebased onto it when that applies
  cleanly. On a conflict, the branch is kept as `backup/<clone>/<branch>`;
  resolve with `wt reconcile <branch>`, then run `wt sync` again.
- **Uncommitted and untracked changes:** `backup/<clone>/wip/<branch>`, built
  in a scratch index. Your worktree, index and stashes stay as they were.
- **Commits on `main` that GitHub lacks:** `backup/<clone>/main`.
- **Stashes:** `backup/<clone>/stash-<sha>`. Restore anywhere with
  `git fetch && git stash apply origin/backup/<clone>/stash-<sha>`.
- **Detached commits:** `backup/<clone>/detached-<sha>`.

Several clones of one repo, start to finish:

```bash
for clone in ~/Developer/Personal/app ~/Dropbox/Zysys/Software/app; do wt -C "$clone" sync; done
wt -C ~/Developer/Personal/app tidy   # the clone you keep
repo-retire check ~/Dropbox/Zysys/Software/app
```

`wt sync` exits 1 while a branch conflicts, a push fails, or a file over
`DEV_PROFILE_SYNC_MAX_FILE_MB` (default 50) had to be left out, so loops and
`wt tidy` stop there. A nested repository is reported; run `wt sync` inside it.
Each clone keeps its id in `git config dev-profile.sync-clone`.

Cleanup never deletes `backup/` refs: restore what you need, then delete them
yourself. `--pushed` keeps a worktree that holds ignored files (`.env`, local
config) the main checkout lacks, and says which. Tool state that regenerates
itself does not count: `DEV_PROFILE_PRUNE_DISPOSABLE` lists it (default `.trunk`).

Preview with `wt sync -- --dry-run` or `wt tidy -- --dry-run`.

## Repo contract

A repo inherits the profile and commits nothing the profile already owns. A repo
must not contain:

- `.prettierrc*`, `.prettierignore`
- `lefthook.yml`, `.trunk/`
- a copied `.golangci.yml`
- `.editorconfig`, `.markdownlintrc`, `.yamllint`
- `renovate.json`, `mise.lock`
- a `go =`, `node =` or `python =` pin in `mise.toml` that only repeats the profile

A repo may contain a `mise.toml` with repo-specific tasks and tools the profile
lacks. Put a one-line reason beside any pin that differs from the profile. A
repo may also keep the language's own files: `go.mod`, `package.json`,
`composer.json`, `pyproject.toml`, `svelte.config.js`, `vite.config.ts`.

### Fixtures and generated files are not source

Formatters and linters format source. Goldens, fixtures and generated output are
compared or consumed verbatim, so touching them breaks tests. The profile skips
`testdata/` and `fixtures/` at any depth, and `generated/`. Put such files there
and no ignore file is needed.

Do not "format the goldens too". A golden's format is then defined by a
third-party formatter's version. A formatter bump would change the goldens with
no code change.

### Escape hatch

A path that cannot move, such as a published schema directory or a generated
file at a fixed path, keeps a `dprint.jsonc` of exactly this shape:

```jsonc
{
  "extends": "~/.local/share/dev-profile/dprint.jsonc",
  "excludes": ["schemas/"]
}
```

dprint expands the leading `~`, so the same file works on every machine where
the profile is rendered to its default path (`mise bootstrap` does this, and
so must a CI runner using the profile). Never write a `/Users/...` path
there: it breaks on other machines and in CI.

Put only `excludes` in it. `excludes` here adds to the profile's list, so the
profile's own entries (`node_modules`, `testdata`, `generated` and the rest)
stay excluded and you list only the extra paths.

`mise run doctor` in a repo warns about each item above that it finds, plus a
`go`, `node`, `python` or `php` pin that repeats the profile's. The warning
becomes an error after the sweep of existing repos.

## Versions

- Runtimes pin to the minor (`go = "1.27"`) or, for Node, the major
  (`node = "24"`), so patch releases arrive with no edit.
- Linters and one-off tools pin exactly, so each weekly `bump` PR shows one
  reviewable change per tool.
- `latest` is never allowed. The test rejects it.
- No `mise.lock` anywhere. The profile is the lock.
- The bot bumps within a pin's depth. A person bumps major-only pins. The `bump`
  PR merges itself when CI passes.

## Adding a tool

A tool is one file, `tools/<category>/<name>.pkl`, amending `lib/Tool.pkl`.
The file name is the hk step name. Nothing else lists it: `profile.pkl`
glob-imports the directory and derives the hooks, the mise pins and the
generated scripts from it.

The template's fields:

- `doc`: one line, what it does and why.
- `pin`: the mise pin, when this profile installs the tool. Omit it when the
  runtime (go, node) or the repo (`vendor/bin`, `node_modules`) provides it.
- `glob` or `types`: the files, as hk globs or hk file types. A hook entry
  without its own inherits them.
- `on`: the hk step per hook. `pre-commit` runs on the staged files: a `fix`
  rewrites and is restaged, a `check` is a guard that blocks the commit.
  `pre-push` runs on the pushed range in check mode and must have a `check`.
  `depends` orders a step after others in the same hook, by hk step name.
- `afterFixers`: a pre-commit `check` that must see the result of every fixer
  runs after all of them, as go-vet does after go fix.
- `scripts`: generated `bin/dev-profile-<x>` scripts, called by name from the
  commands. The hidden `bash`, `nearestUp`, `goModules` and `goPackages`
  fragments are available inside them.
- A tool in both hooks with different steps is `<name>-fix` or
  `<name>-staged` at commit and `<name>` at push; a tool with the same step in
  both keeps one name.

### Worked example: go mod tidy

The simplest version is seven lines on hk's builtin and is enough for a
single-module repo:

```pkl
amends "../../lib/Tool.pkl"

doc = "Keep go.mod and go.sum in step with the imports."
on {
  ["pre-commit"] = (module.builtins.gomod_tidy) { depends = List("go-imports") }
  ["pre-push"] = module.builtins.gomod_tidy
}
```

Inside `on`, inherited members such as `builtins` need the `module.` prefix.

Review found two things the builtin gets wrong here, and both are typical of
what a real tool needs. Tidy must run after every fixer that can change an
import, not just goimports: go fix and golangci's `exptostd` swap a third-party
package for stdlib, which leaves a stale `require`. And a module that a parent
`go.work` omits must run with `GOWORK=off`, as the other Go steps do. So the
shipped `tools/go/go-mod-tidy.pkl` adds a small wrapper script on the shared
`goModules` fragment, which groups the given files by module and knows each
module's workspace membership:

```pkl
glob = List("**/*.go", "**/go.mod", "**/go.sum")
on {
  ["pre-commit"] {
    depends = List("go-imports", "go-fix", "go-modernize", "golangci-lint-fix")
    stage = List("**/go.mod", "**/go.sum")
    fix = "dev-profile-go-mod-tidy {{files}}"
  }
  ["pre-push"] { check = "dev-profile-go-mod-tidy --diff {{files}}" }
}

local goModTidy = #"""
  \#(bash)
  (($#)) || exit 0
  \#(goModules)
  ...
  """#

scripts { ["dev-profile-go-mod-tidy"] = goModTidy }
```

Step by step, that was:

1. Create `tools/go/go-mod-tidy.pkl` with `doc`, `glob` and the two `on`
   entries. `depends` names the fixers it must follow.
2. Write the script as a `local` raw string and register it under `scripts`.
   `mise run doctor` fails if a step names a `dev-profile-*` command that no
   tool renders.
3. Add `tests/go-mod-tidy-fixture.sh` (real go and git, no network) and its
   line in the doctor task.
4. `mise run test`. `pkl test` fails on the snapshot, as it should: review the
   diff, then `pkl test --overwrite tests/profile.test.pkl` to accept it.
5. `mise run explain go-mod-tidy` to confirm where it landed: `go-mod-tidy-fix`
   at commit after the Go fixers, `go-mod-tidy` at push.

Then `mise run bootstrap` (or `mise run install-live`) to deploy the render.

## Keeping the pins current

`mise run bump` asks mise for the latest release of every pin (tool pins, the
dprint plugins, the hk package the Pkl sources import), rewrites the ones that
are behind, and regenerates the snapshot. A pin shorter than the release keeps
its depth: `go = "1.27"` moves to `1.28` only when a 1.28 release exists. A
major-only pin such as `node = "24"` is never moved across majors: the PR
lists it as held, for a person to bump. The `bump` workflow runs it every Monday and
opens a PR with the table of changes, dispatches `ci` on it, and arms
auto-merge: the PR merges itself once the `test` check passes, and stays open
and red when it does not.

`latest` is not allowed for a mise pin: the bot skips it, the snapshot becomes
machine-dependent, and SAH's profile already forbids it. `mise run doctor` fails
on one, through the "no mise pin is `latest`" fact in `tests/profile.test.pkl`.
