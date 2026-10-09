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
| `tests/profile.test.pkl` | invariants and a snapshot of what each hook runs            |
| `tests/*-fixture.sh`     | the generated scripts against real git and go               |

## What runs when

| Event                 | Files           | Mode                       | Steps                                        |
| --------------------- | --------------- | -------------------------- | -------------------------------------------- |
| save (Neovim)         | the buffer      | format                     | dprint, from the language's `dprint` binding |
| `git commit`          | staged          | fix, restaged; checks block| every tool's `pre-commit` entry, dprint last |
| `git push`            | the pushed range| check only                 | every tool's `pre-push` entry                |
| `hk fix` / `hk check` | modified        | fix / check                | the `pre-commit` entries                     |
| `hk check --slow --all` | whole tree    | check                      | the `pre-commit` and `pre-push` entries      |
| `mise run lint`, `scan`, `test`, `ci` | whole tree | native tools  | the contract adapters, not hk                |

A `fix` rewrites what it safely can and never blocks: push judges the rest. A
`check` may block. Per-file push checks run on the files changed since the
default branch; whole-program linters (golangci-lint, go vet, clippy) fail only
on issues new in that range, so old debt never blocks a push. Full-tree runs are
explicit, never in hooks. CI judges the full tree.

`mise run explain go` prints the resolved plan for one tool or one `tools/`
category: the step name per hook, its command, files and ordering.

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
- `scripts`: generated `bin/dev-profile-<x>` scripts, called by name from the
  commands. The hidden `bash`, `nearestUp`, `goModules` and `goPackages`
  fragments are available inside them.
- A tool in both hooks with different steps is `<name>-fix` or
  `<name>-staged` at commit and `<name>` at push; a tool with the same step in
  both keeps one name.

### Worked example: go mod tidy

The simplest version is eight lines on hk's builtin and is enough for a
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
