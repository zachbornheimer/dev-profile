# Our hk configuration, step by step

The shared config is `~/Developer/Personal/dev-profile/hk/hk.pkl`, reached by every repository through
`~/.config/hk/config.pkl` (hk's _user_ config; additive merge, project wins collisions). Steps live in
two mappings, `local fixers` and `local gates`, and the hooks `commit-msg`, `pre-commit`, `pre-push`
plus the implicit `check`/`fix` apply them. 47 step names; `hk validate` keeps them honest.

Audit of 2026-11-05 on this machine: 28 steps are a bare tool over `{{files}}` behind the
`dev-profile-changed-files` wrapper, 6 are whole-tree tools (`go vet ./...`, `govulncheck ./...`,
`cargo-deny --workspace`, `golangci-lint`, `destroyed-symlinks`, `forbid-submodules`), 2 scan a
directory or range rather than their files (`betterleaks dir`, `gitleaks git --log-opts=<range>`), and
the rest are policy wrappers. Under hk's model every wrapped step is a step whose real scope hk cannot
lock, and the wrapper is the only place "judge what this push introduces" can live.

## Steps hk can own outright (builtin supplies the command, we supply globs/exclusions)

| our step name                      | builtin                                    | builtin's commands                                                                                                                                                                                                                              |
| ---------------------------------- | ------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `dprint`                           | `Builtins.dprint`                          | check `dprint check --allow-no-files {{files}}`; check_list_files `… --list-different {{files}}`; fix `dprint fmt --allow-no-files {{files}}`                                                                                                   |
| `go-imports`                       | `Builtins.go_imports`                      | check_diff `goimports -d {{files}}`; check_list_files `goimports -l {{files}}`; fix `goimports -w {{files}}`                                                                                                                                    |
| `markdownlint`, `markdownlint-fix` | `Builtins.markdown_lint`                   | check `markdownlint {{files}}`; fix `markdownlint --fix {{files}}`                                                                                                                                                                              |
| `newlines`                         | `Builtins.newlines`                        | check_diff `hk util end-of-file-fixer --diff {{files}}`; fix `… --fix {{files}}`                                                                                                                                                                |
| `trailing-whitespace`              | `Builtins.trailing_whitespace`             | check_diff `hk util trailing-whitespace --diff {{files}}`; fix `… --fix {{files}}`                                                                                                                                                              |
| `tofu`, `tofu-fix`                 | `Builtins.tofu`                            | check `tofu fmt -check {{files}}`; check_diff `hk util format-diff {{files}} -- tofu fmt -`; fix `tofu fmt {{files}}`                                                                                                                           |
| `hadolint`                         | `Builtins.hadolint`                        | `hadolint {{files}}`                                                                                                                                                                                                                            |
| `actionlint`                       | `Builtins.actionlint`                      | `actionlint {{files}}`, `batch = true`                                                                                                                                                                                                          |
| `pinact`                           | `Builtins.pinact`                          | check `pinact run --verify-comment --check {{files}}`; check_diff `hk util sarif-diff -- pinact run --verify-comment --check --format sarif {{files}}`; fix `pinact run --verify-comment {{files}}`                                             |
| `zizmor`                           | `Builtins.zizmor`                          | check `zizmor --no-progress {{files}}`; fix `zizmor --no-progress --fix {{files}}`                                                                                                                                                              |
| `go-vet`                           | `Builtins.go_vet`                          | `go vet ./...`, `workspace_indicator = "go.mod"`, `dir = "{{workspace}}"`                                                                                                                                                                       |
| `govulncheck`                      | `Builtins.go_vuln_check`                   | `govulncheck ./...`, workspace                                                                                                                                                                                                                  |
| `cargo-deny`                       | `Builtins.cargo_deny`                      | `cargo-deny --locked --workspace check`, `workspace_indicator = "Cargo.toml"`                                                                                                                                                                   |
| `kube-linter`                      | `Builtins.kube_linter`                     | `kube-linter lint --fail-if-no-objects-found {{files}}` + its own exclude list                                                                                                                                                                  |
| `kubeconform`                      | `Builtins.kubeconform`                     | `kubeconform -summary -strict -ignore-missing-schemas {{files}}` + its exclude list (shorter than ours: it lacks `**/values-*.yaml`)                                                                                                            |
| `case-conflicts`                   | `Builtins.check_case_conflict`             | `hk util check-case-conflict {{files}}`                                                                                                                                                                                                         |
| `check-executables-have-shebangs`  | `Builtins.check_executables_have_shebangs` | `hk util check-executables-have-shebangs {{files}}`                                                                                                                                                                                             |
| `check-symlinks`                   | `Builtins.check_symlinks`                  | `hk util check-symlinks {{files}}`                                                                                                                                                                                                              |
| `destroyed-symlinks`               | `Builtins.destroyed_symlinks`              | `hk util destroyed-symlinks`                                                                                                                                                                                                                    |
| `forbid-submodules`                | `Builtins.forbid_submodules`               | `hk util forbid-submodules`                                                                                                                                                                                                                     |
| `merge-conflicts`                  | `Builtins.check_merge_conflict`            | `hk util check-merge-conflict --assume-in-merge {{files}}`                                                                                                                                                                                      |
| `private-keys`                     | `Builtins.detect_private_key`              | `hk util detect-private-key {{files}}` — the builtin's command **without** its `types = ["text"]` filter, which drops an extension-less file holding a key: hk reads that file as non-text.                                                     |
| `betterleaks`                      | `Builtins.betterleaks`                     | `betterleaks dir --redact --verbose --no-banner --confidence medium {{files}}` — same caveat: the builtin filters candidates to `types = ["text"]`, so the step keeps the command and not the filter.                                           |
| commit-message check               | `Builtins.check_conventional_commit`       | same util our grep emulates: types default `build,chore,ci,docs,feat,fix,perf,refactor,revert,style,test`, plus `allowed_scopes` (unset = any scope, empty list = unscoped only); `fixup!`/`squash!`/`amend!`/`Merge …`/`Revert "` titles pass. |

## Steps where the builtin changes behavior (decide, do not drift)

| our step                      | builtin                            | difference                                                                                                                                                                                                                                                                         |
| ----------------------------- | ---------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `oxlint`, `oxlint-fix`        | `Builtins.ox_lint`                 | builtin adds **`--deny-warnings`** to both check and fix; ours is plain `oxlint`. Warnings start blocking.                                                                                                                                                                         |
| `ruff`, `ruff-fix`            | `Builtins.ruff`                    | builtin: check `ruff check --force-exclude`, check_diff `--diff --exit-non-zero-on-fix` + `check_after_diff = true`, fix `--fix`. Ours pins rule families (`--extend-select UP,FURB,SIM,PERF,C4,PIE`) and `--fix-only --unsafe-fixes`, so amending is required to keep the policy. |
| `check-added-large-files`     | `Builtins.check_added_large_files` | the util has **no added-only flag** (`--maxkb` only, default 500 KB): it judges every path it is handed. Our `dev-profile-changed-files --added` narrowing is therefore the only place that policy can live — keep the wrapper, or accept judging merge-carried files too.         |
| `strict-json`                 | `Builtins.jq`                      | the jq builtin is a **formatter** (check_diff plus a fix that rewrites files with sorted keys), so adopting it would make pre-push rewrite JSON files. Ours validates JSON per file without rewriting. Different intent.                                                           |
| `no-commit-to-default-branch` | `Builtins.no_commit_to_branch`     | the util protects `main,master` by default (`--branch` takes a comma list) and its message is fixed; ours adds the `DEV_PROFILE_ALLOW_DEFAULT_BRANCH_PUSH` escape hatch and its own wording, so adopting drops the escape hatch.                                                   |

## Steps that must keep their wrapper (the tool needs more than a file list)

| step                  | wrapper                                               | why it cannot be a builtin                                                                                                                                                                                                                            |
| --------------------- | ----------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `stylelint`           | `dev-profile-changed-files dev-profile-stylelint-fix` | stylelint exits 78 with a configuration error when a repo supplies no config, and hk prints that stderr whenever any unrelated step fails; the wrapper absorbs it and falls back to the profile config.                                               |
| `gosec`               | `dev-profile-gosec-packages`                          | gosecs the packages holding the pushed files but fails only on findings **in those files**, so debt in an untouched file of the same package cannot block a push. `Builtins.go_sec` is `gosec ./...` per workspace.                                   |
| `golangci-lint`       | `dev-profile-golangci-ratchet`                        | reports only issues the branch adds over origin's default branch, and carries **no fixer** because a whole-workspace `--fix` rewrote every module mid-push and the steps after it judged the broken files.                                            |
| `foxguard-typescript` | `dev-profile-foxguard-introduced`                     | scans only the introduced files through `--changed-files-from` and is budgeted (`DEV_PROFILE_FOXGUARD_BUDGET`, default 1200s, fail-closed) because an unbudgeted scan wedges past the runner's deadline.                                              |
| `gitleaks`            | inline range scan                                     | scans the **pushed commit range** (`git --log-opts`), not the working tree as `Builtins.gitleaks` does.                                                                                                                                               |
| `brakeman`            | `dev-profile-brakeman`                                | brakeman takes one application path, so the wrapper scans each file from the root that holds it, and blocks only on warnings the push introduces over the merge base (whole-app warnings such as EOLRails are printed as pre-existing, never hidden). |
| `bundle-audit`        | `dev-profile-bundle-audit`                            | operates on a project directory, not a lockfile.                                                                                                                                                                                                      |
| `shellcheck`          | filter + `xargs -r`                                   | needs a file filter (zsh is out of scope) and `-r` so an empty list cannot turn into a usage error.                                                                                                                                                   |

All of the above should be declared `exclusive = true` (plus a comment naming the real scope) if they
stay wrappers: hk otherwise schedules them as if they only touched their step's files.

## The hook wrapper, and the tests that pin it

`bin/dev-profile-pre-push` reads the ref list from stdin, refuses a push it cannot measure
(`dev-profile-push-base`, or refs that do not match the ref pattern), measures the introduced set once
with `dev-profile-push-introduced`, exports it as `DEV_PROFILE_PUSH_INTRODUCED`, and runs
`hk run pre-push`. Handing hk that list with `--files0-from <file>` is hk's documented way to set the
candidate set — and pre-push **reserves stdin**, so it must be a file path, never `-`.

Fixtures that fail if the mechanism changes:

- `tests/pre-push-refs-fixture.sh` — greps the wrapper's `candidate file(s)` (line 83) and
  `1 of 1 candidate file(s) introduced by this push` (line 97).
- `tests/pre-push-upstream-merge.sh` — asserts a named step (markdownlint) ran on an upstream-merge push.
- `tests/pre-push-empty-file-list-fixture.sh` — a pushed private key must fail the push.
- Newer, from main: the foxguard-introduced, gosec, shellcheck-severity, brakeman, semgrep and
  pre-push-refs fixtures, plus the large-file/added-only gate.

Measured 2026-11-05, one change at a time: main's config passes all three pre-push fixtures; main's
config plus the `--files0-from` handoff failed the upstream-merge fixture and the refs fixture's
wrapper-line greps; the builtins conversion with main's wrapper failed all three. Landed in `e0da44c`:
the handoff plus the builtins, with those assertions ported to what the push did rather than to what a
wrapper printed:

- `tests/pre-push-refs-fixture.sh` — case 3 asserts the push passes and a selected step ran; case 4
  pushes a key with the hook disabled, then asserts a push touching only `a.txt` passes while
  `private-keys` still runs. (The old `candidate file(s)` greps pinned the wrapper's own lines, which
  file selection no longer goes through.)
- `tests/pre-push-upstream-merge.sh` — the merge push passes, glob-less `gitleaks` proves the gate ran,
  and no step attributes upstream's findings to the push; the authored cases still require
  `✗ markdownlint` and `MD040`, so the steps are proven to run when the push does introduce files.
- `tests/pre-push-empty-file-list-fixture.sh` — unchanged, and it is what forced `private-keys` off the
  builtin's type filter.

Two hk facts those ports depend on:

- A measurement of `*` is the convention for "no base to measure an introduced set against" (a first
  push to an empty remote): the hook passes no `--files0-from`, and hk's own candidates stand in.
- An empty measurement is passed as an empty file list, so the push judges nothing. That is what makes
  an upstream-merge push — whose branch work is already published — cost no per-file step at all.

## Useful knobs for our shape

- `hk run pre-push --plan` / `--why <step>` / `--stats`, `HK_TIMING_JSON=… hk run pre-push` — inspect
  selection and per-step time without pushing.
- `HK_FILE=hk/hk.pkl hk validate` in a worktree before merging a config change.
- Hook `timeout` is the only runtime bound hk offers per hook; risky steps carry their own inline
  `timeout`.
- `hk test` runs the `tests { }` blocks a step declares, if we ever want hk-native step tests instead of
  bash fixtures.

## `hk util` facts that decide step shapes

- Exit `1` = found a problem, `0` = clean, for every check util. Five utils write files
  (`end-of-file-fixer`, `trailing-whitespace`, `mixed-line-ending`, `fix-byte-order-marker`,
  `fix-smart-quotes`); the rest only report.
- `destroyed-symlinks` and `forbid-submodules` scan the **whole repository** when given no paths — that is
  why they are whole-tree steps here, not per-file ones.
- `check-added-large-files` takes `--maxkb` (default 500) and nothing else; `--added` is ours.
- `hk util format-diff {{files}} -- <cmd>` (with `{}` for the path) is how a formatter builtin gets a
  patch instead of rewriting files; `hk util sarif-diff` does the same for a SARIF log.
- A step's failure makes `hk run <event>` exit `1`, which aborts the git operation; `allow_failure`
  reports the failure without failing the hook, and a hook `timeout` fails the hook so the push is blocked.
