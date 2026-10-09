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

| Path                   | Role                                                   |
| ---------------------- | ------------------------------------------------------ |
| `mise.toml`            | kernel: Pkl pin and tasks                              |
| `profile.pkl`          | languages, runtime pins, live paths; derives the hooks |
| `tools/<category>/`    | one file per tool: pin, scripts, step per hook         |
| `lib/Tool.pkl`         | the template every tool file amends                    |
| `lib/hk.pkl`           | the hk config, assembled from the tools                |
| `lib/render.pkl`       | one renderer per generated file                        |
| `tests/profile.test.pkl` | invariants and a snapshot of what each hook runs     |

Phases: save formats; commit converges (format, autofix, modernize, restage) on
the staged files and never blocks on what it can fix; push only checks (no
fixing) what is being uploaded: per-file linters run on the files changed since
the default branch, and whole-program linters (golangci-lint, go vet, clippy)
fail only on issues new in that range, so old debt never blocks a push. Full-tree
runs are explicit (`mise run lint`, `mise run scan`, `hk check --slow --all`),
never in hooks. CI judges the full tree.

## Adding a tool

A tool is one file, `tools/<category>/<name>.pkl`, amending `lib/Tool.pkl`.
The file name is the hk step name. It declares what the tool can do; the `on`
mapping says when it runs:

```pkl
amends "../../lib/Tool.pkl"

doc = "Wrap long Go lines at commit."
pin { id = "go:github.com/segmentio/golines"; version = "0.12.2" }
on {
  ["pre-commit"] { glob = List("**/*.go"); depends = List("go-imports"); fix = "golines -w {{files}}" }
}
```

- `pre-commit` runs on the staged files. A `fix` rewrites and is restaged and
  never blocks; a `check` is a guard that blocks the commit.
- `pre-push` runs on the pushed range in check mode and may block; a tool
  listed there must have a `check`.
- `hk fix` and `hk check` reuse the pre-commit entries; `hk check --slow`
  adds the pre-push ones.
- Start from an hk builtin with `(module.builtins.golangci_lint) { ... }`.
  A wrapper script goes in `scripts { ["dev-profile-<x>"] = ... }` and is
  called by name.
- A tool in both hooks with different steps is `<name>-fix` or
  `<name>-staged` at commit and `<name>` at push.

Then `mise run test`. The snapshot in `tests/profile.test.pkl-expected.pcf`
records what each hook runs; after an intended change, regenerate it with
`pkl test --overwrite tests/profile.test.pkl` and review the diff.
`mise run explain go` prints the resolved plan for a tool or a category.
