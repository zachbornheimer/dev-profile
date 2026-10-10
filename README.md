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
| `lib/pr.pkl`             | the `wt pr` family: publish, watch to merge, prune          |
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

`lib/pr.pkl` renders three scripts and the aliases that call them. None of
them prompt, so loops and scripts can drive them.

| Alias         | Does                                                                |
| ------------- | ------------------------------------------------------------------- |
| `wt pr [B]`   | commit pending work, push (never force), reuse or open a PR         |
| `wt pr-draft` | same, as a draft                                                    |
| `wt pr-auto`  | same, then watch CI, merge when green, notify, remove the worktree  |
| `wt ship`     | `pr-draft` for the current worktree; skips what has nothing to send |
| `wt ship-all` | `ship` in every worktree                                            |
| `wt prune`    | `wt step prune`, plus branches whose tip is a PR GitHub merged      |

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
(`DEV_PROFILE_PR_MERGE_METHOD` overrides).
After the merge it fast-forwards your local default branch where it is checked
out, so that checkout's `post-merge` hooks run. Here, `mise run install-git-hooks`
adds one: a pull or merge that moves `main` runs `mise run generate`, so the
live profile follows `main`.

Preview a prune with `wt prune -- --dry-run`; wt reserves a bare `--dry-run`
on aliases.

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
lists it as held, for a person to bump. `latest` pins are left alone. The `bump` workflow runs it every Monday and
opens a PR with the table of changes, dispatches `ci` on it, and arms
auto-merge: the PR merges itself once the `test` check passes, and stays open
and red when it does not.
