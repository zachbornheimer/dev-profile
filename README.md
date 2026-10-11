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

| Path                     | Role                                                          |
| ------------------------ | ------------------------------------------------------------- |
| `mise.toml`              | kernel: Pkl pin and verb tasks; the rest are in `mise-tasks/` |
| `profile.pkl`            | languages, runtime pins, live paths; derives the hooks        |
| `tools/<category>/`      | one file per tool: doc, pin, scripts, its step per hook       |
| `lib/Tool.pkl`           | the template every tool file amends                           |
| `lib/hk.pkl`             | the hk config, assembled from the tools                       |
| `lib/script.pkl`         | bash fragments the tool scripts share                         |
| `lib/render.pkl`         | one renderer per generated file                               |
| `lib/contract.pkl`       | the repo task contract (`mise run lint`, `test`, `scan`...)   |
| `lib/pr.pkl`             | `wt pr`, `wt pr-draft`, `wt pr-auto`                          |
| `lib/done.pkl`           | `wt done`: restack, push, pull requests, prune, drop          |
| `lib/sync.pkl`           | backup scripts the fixtures call; no worktrunk alias          |
| `lib/retire.pkl`         | retire script the fixture calls; no worktrunk alias           |
| `tests/profile.test.pkl` | invariants and a snapshot of what each hook runs              |
| `tests/*-fixture.sh`     | the generated scripts against real git and go                 |
| `mise-tasks/bump`        | bump every outdated pin to its latest release                 |
| `.github/workflows/`     | `ci` runs doctor on every push and PR; `bump` runs weekly     |

## What runs when

| Event                   | Files            | Mode                        | Steps                                                                                   |
| ----------------------- | ---------------- | --------------------------- | --------------------------------------------------------------------------------------- |
| save (Neovim)           | the buffer       | format                      | dprint, from the language's `dprint` binding                                            |
| `git commit`            | staged           | fix, restaged; checks block | every tool's `pre-commit` entry, dprint last                                            |
| `git push`              | the pushed range | check only                  | every tool's `pre-push` entry                                                           |
| `hk fix` / `hk check`   | modified         | fix / check                 | the `pre-commit` entries, without the default-branch commit guard                       |
| `hk check --slow --all` | whole tree       | check                       | the `pre-commit` and `pre-push` entries                                                 |
| `mise run lint`         | whole tree       | check                       | `hk check --all --slow --profile lint` (commit guards off) plus the suppressions report |
| `mise run test`, `scan` | whole tree       | native tools                | the contract adapters in `lib/contract.pkl`, not hk                                     |
| `mise run ci`           | whole tree       | all of the above            | `lint`, then `test`, then `scan`                                                        |

A `fix` rewrites what it safely can and never blocks: push judges the rest. A
`check` may block. Per-file push checks run on the files changed since the
default branch; whole-program linters (golangci-lint, go vet, clippy) fail only
on issues new in that range, so old debt never blocks a push. Full-tree runs are
explicit, never in hooks. CI judges the full tree.

`strict-json` replaces the retired pre-commit `check-json`: dprint's JSON plugin
accepts comments and trailing commas, so `jq empty` parses every `*.json` strictly
at commit, push and lint. `*.jsonc`, `tsconfig*.json`, `jsconfig*.json`,
`.devcontainer/` and `.vscode/` stay lenient.

`mise run explain go` prints the resolved plan for one tool or one `tools/`
category: the step name per hook, its command, files and ordering.

## Pull requests from wt

`lib/pr.pkl` renders two scripts and the aliases that call them. None of
them prompt, so loops and scripts can drive them.

| Alias         | Does                                                               |
| ------------- | ------------------------------------------------------------------ |
| `wt pr [B]`   | commit pending work, push (never force), reuse or open a PR        |
| `wt pr-draft` | same, as a draft                                                   |
| `wt pr-auto`  | same, then watch CI, merge when green, notify, remove the worktree |

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
overrides the choice. `DEV_PROFILE_PR_MESSAGE="fix: thing"` commits pending
work with that message instead of one the LLM writes. The watcher merges only after every check passes, even
where the branch has no protection, using the repo's default merge method
(`DEV_PROFILE_PR_MERGE_METHOD` overrides). Where GitHub refuses auto-merge
(a private repo on the Free plan), `pr-auto` merges directly once checks pass.
After the merge it fast-forwards your local default branch where it is checked
out, so that checkout's `post-merge` hooks run. Here, `mise run install-git-hooks`
adds one: a pull or merge that moves `main` runs `mise run generate`, so the
live profile follows `main`.

## End of day: `wt done`

`lib/done.pkl` renders `dev-profile-done` and the `wt done` alias. Flags do not
imply each other. Worktrunk may swallow flags, so from the alias pass them
after `--`.

| Command     | Does                                                                                                                                                               |
| ----------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `wt done`   | fetch origin, fast-forward the default branch when it is strictly behind, restack with `wt-sync --all`                                                             |
| `--commit`  | commit uncommitted work, stashes, and detached HEAD first. Without it, those branches are skipped                                                                  |
| `--push`    | push what restacked. A rewritten branch uses `--force-with-lease`. A conflict goes to `backup/conflicts/<clone>/<branch>` under that clone's id, not the real name |
| `--pr`      | open pull requests for branches this run pushed. Needs `--push`. Conflict pull requests are drafts into the branch they diverged from                              |
| `--prune`   | remove local worktrees and branches whose tips match origin, and delete origin branches already in the default branch                                              |
| `--drop`    | Trash the clone when nothing was skipped, every tip is on origin, and no linked worktree remains                                                                   |
| `--dry-run` | print the plan. `git fetch` is the only change                                                                                                                     |

A default branch that is strictly ahead of origin is pushed as
`backup/main/<clone>` and, with `--pr`, opened as an auto-merge pull request.
A diverged default branch uses the conflict draft instead. Stashes, `wip`
snapshots, and detached commits are pushed and do not become pull requests.
`--prune` never deletes `backup/*`, the default branch, open pull requests, or
anything this run skipped. Ignored files such as `.env` are not pushed; `--drop`
leaves them in the Trash. A file over `DEV_PROFILE_SYNC_MAX_FILE_MB` (default
50) or a nested repository refuses `--drop`.

`wt sync` is the stacked restack command (`wt-sync`). `dev-profile-sync` and
`dev-profile-retire` stay on disk for their fixtures and have no alias.

```bash
wt done -- --dry-run
wt done -- --dry-run --commit --push --pr --prune --drop
```

## Repo contract

A repo inherits the profile and commits nothing the profile already owns. A repo
must not contain:

- `.prettierrc*`, `.prettierignore`
- `lefthook.yml`, `.trunk/`
- a copied `.golangci.yml`
- `.editorconfig`, `.markdownlintrc`, `.yamllint`
- `renovate.json`, `mise.lock`
- a `go =`, `node =` or `python =` pin in `mise.toml` that only repeats the profile

A repo's `.git/hooks/` must not hold files from retired hook managers (lefthook,
zq, trunk, husky, yorkie, pre-commit.com); only the global hk hooks run.
`wt switch` renames them to `<name>.retired-by-dev-profile`
(`dev-profile-retire-legacy-hooks [repo]`, reversible), and `mise run doctor` warns about any left.

A repo may contain a `mise.toml` with repo-specific tasks and tools the profile
lacks. Put a one-line reason beside any pin that differs from the profile. A
repo may also keep the language's own files: `go.mod`, `package.json`,
`composer.json`, `pyproject.toml`, `svelte.config.js`, `vite.config.ts`.

### Task contract

Verbs: `setup`, `build`, `fmt`, `lint`, `test`, `scan`, `doctor`, `ci`. Each has a
`profile:<verb>` task (the work) and a plain `<verb>` twin that depends on it.

- A repo overrides a verb only to add work: `depends = ["profile:<verb>"]` plus its own `run`.
- Never redefine `ci`. `profile:ci` runs `lint`, `test` and `scan` through the repo's verb overrides.
- Repo-specific tasks that are not verbs (`review-mail`, `install`, `deploy`, `package`, `migrate`) are file tasks under `mise-tasks/` (`mise-tasks/<name>` or `mise-tasks/<group>/<name>`), not entries in `mise.toml`. They keep their task names, have no profile dependency, and `ci` does not run them.
- Deploy-class tasks are kept, never dropped, and never run by the profile.

`mise.toml` holds only verb extensions:

```toml
[tasks.test]
depends = ["profile:test"]
run = "./scripts/integration.sh"
```

A non-verb task is an executable file, for example `mise-tasks/deploy`:

```bash
#!/usr/bin/env bash
#MISE description="Deploy to production"
./scripts/deploy.sh
```

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

### Outside a code root

A clone under `/tmp/repos/<org>/<repo>` has no code-root `mise.toml`, so
`profile:ci` and the tool pins are not in scope. Run any command through the
profile's entry point instead:

```sh
~/.local/share/dev-profile/bin/dev-profile-env -- mise run profile:ci
~/.local/share/dev-profile/bin/dev-profile-env --root personal -- mise run ci
~/.local/share/dev-profile/bin/dev-profile-env --root sah -- mise run ci
```

It builds an isolated `MISE_CONFIG_DIR` under `~/.cache/dev-profile/env-<root>`
(override with `DEV_PROFILE_CACHE`): the pins and contract tasks from
`mise-profile.toml`, plus the root overlay `--root` names (`personal`, or `sah`,
the SAH root `mise.toml`, or `SAH_ROOT_OVERLAY`). It never touches the live
`~/.config` and never writes into the repo. `--print` shows the `export` line for
`eval`. Do not point `MISE_GLOBAL_CONFIG_FILE` at an overlay: that drops the pins,
so hk's markdownlint and betterleaks have no version.

The CI action below runs the same script, with `--link-only`, against
`~/.config/mise`.

## Versions

- Runtimes pin to the minor (`go = "1.27"`) or, for Node, the major
  (`node = "24"`), so patch releases arrive with no edit.
- Linters and one-off tools pin exactly, so each weekly `bump` PR shows one
  reviewable change per tool.
- `latest` is never allowed. The test rejects it.
- No `mise.lock` anywhere. The profile is the lock.
- The bot bumps within a pin's depth. A person bumps major-only pins. The `bump`
  PR merges itself when CI passes.

## CI runners

A runner has no `~/.config/mise/conf.d/dev-profile.toml`, so a repo with no tool
pins of its own gets no tools. This repo is also a composite action that does what
`mise bootstrap` does for tools: it renders the profile (`mise run generate`) to
`~/.local/share/dev-profile`, links `mise-profile.toml` into mise's global
`conf.d`, caches the installs and runs `mise install`. The global config holds
the pins and the contract tasks, so `mise run ci` works in any repo, in a code
root or not. A repo's own `mise.toml` still overrides it, and the dprint escape
hatch above resolves. Runners get tools only, no hooks or worktrunk.

```yaml
- uses: zachbornheimer/dev-profile@main
- run: mise run ci
```

The ref is `@main`, not a tag: the Mac tracks main too. For a reproducible run,
pin a commit SHA. The `action` job in `ci.yml` tests it end to end.

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
