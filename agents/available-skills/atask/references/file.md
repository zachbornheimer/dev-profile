# How to file

Confirm flags with `atask help add` on the binary you will run.

## Inspect

```bash
atask list --json
atask list ready --json
atask list draft --json
atask show EXISTING_ID --json
```

Match on title, outcome, and overlapping proofs before `add`.

## Single task

```bash
atask add "Short outcome title" \
  --outcome "The observable end state" \
  --accept "Binary criterion 1" \
  --constraint "Do not touch PATH" \
  --proof "go_test: ./pkg name=TestTheOutcome" \
  --regression "go_test: ./pkg size=medium" \
  --parent GROUP_REF \
  --requires OTHER_ID \
  --key stable-key
```

`--proof` (30 s) and `--regression` are both required to be claimable. Missing
either makes a draft (`◌`, see `atask list draft`). Any check spec takes
`size=small|medium|large|eternal` as its last option (30/300/900 s/no budget);
omitted, a proof is small and a regression takes its preset's default. Repeat `--accept` / `--requires` as needed.

Presets, `"PRESET: SUBJECT [k=v]"`: `run` (raw command, `expect=`), `ci`,
`lint`, `build`, `go_test` (`name=`), `py_test`, `js_test`, `rs_test`,
`<lang>_test` (pl, php, rb, swift, sh), `playwright_run` (`grep=`, `project=`),
`file_exists`, `file_absent` (`depth=`), `file_blake3` (`hash=`), `grep`
(`pattern=`, `absent=`), `http_ok` (`status=`, `body=`), `pr_merged`.

After completion: `--on-complete "PRESET: ..."` (waited, 900 s) or
`--on-complete-detach "PRESET: ..."`.

## Plan file (atomic batch)

```bash
atask add -f plan.yaml
# or
atask add --plan '{"tasks":[...]}'
```

Items carry the same fields as the flags (`key`, `title`, `outcome`,
`acceptance`, `parent`, `requires`, proof, regression, size). Identical **open**
titles reuse the oldest live id.

## Update instead of clone

```bash
atask update ID --proof "go_test: ./pkg name=TestTheOutcome" --regression "go_test: ./pkg"
atask update ID --archive --reason "duplicate of at-xxxxxx"
```

Do not `--archive` a claimed or completed task, or one with live dependents.

## Project

`--project NAME|ID` is the only selector; default `general`. No positional
project on `list`. Enrolled repo (`atask init` already) uses that project.
Repeat `--project` on `add`/`update` for multi-project tasks; the first is the home (repo, worktree, branch) and is fixed after the first claim.

Agents do not run `atask project`. Humans set `--target-branch` and
`--attempts` only; a project holds no checks.

Globals: `--project`, `--db`, `--json`.

## After add

```bash
atask show ID --json
atask list --json
```

Report id, title, parent/requires, proof and regression, and whether it is new,
a reuse, or a draft. Then stop unless the caller authorized claim/implement.
