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

| Path             | Role                                 |
| ---------------- | ------------------------------------ |
| `mise.toml`      | kernel: Pkl pin and tasks            |
| `profile.pkl`    | languages, tools, phases, live paths |
| `lib/types.pkl`  | types                                |
| `lib/render.pkl` | one renderer per generated file      |

Phases: save formats; commit converges (format, autofix, modernize, restage) on
the staged files and never blocks on what it can fix; push only checks (no
fixing) what is being uploaded: per-file linters run on the files changed since
the default branch, and whole-program linters (golangci-lint, go vet, clippy)
fail only on issues new in that range, so old debt never blocks a push. Full-tree
runs are explicit (`mise run lint`, `mise run scan`, `hk check --slow --all`),
never in hooks. CI judges the full tree.
