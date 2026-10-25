# Getting a repo onto the Zach devops approach (prune playbook)

Originated from the isa-platform to isa-api cleanup. This file is now the
canonical copy (the Desktop draft is retired). Goal: the repo keeps only what
is truly its own; everything shared comes from the profile root (SAH:
`~/Developer/Software-Automation-Holdings/` from the `platform` repo; personal:
`~/Developer/Personal/` from `dev-profile`). Small reviewable commits, no lost
behavior.

Contract: `~/.claude/rules/devops-standards.md`, `~/.agents/available-skills/mise/SKILL.md`.

## The question for every devops artifact

For each workflow, config, script, task, hook, pin, or tooling doc:
**can we remove it from this repo?**

- Shared by (or useful to) other repos → move it into the profile, delete the copy.
- Duplicates what the root already does → delete.
- Truly repo-specific (this repo's build, deploy, SDK pipeline) → keep, as a mise
  task that extends `profile:<verb>`.
  Profile bugs found along the way (adapter, fixer, shared config) are fixed in the
  profile, never patched per repo.

## Rules that decide every file

1. Automation lives once, in the profile. Per-repo copies are the defect.
2. mise is the only entrypoint. No Makefile task runner; no task runs `make`.
3. Python only through uv (`uv run x.py`); the commit fixer
   `uv-instead-of-python-in-tasks` rewrites bare `python3` in mise tasks; doctor
   fails on python/pip/pipx/poetry/virtualenv. Undeclared deps fail loudly (PEP
   723 header or a uv project).
4. Node through aube.
5. No `|| true` on a check. No inline suppression comments. False positive = fix
   the code. Exceptions only in the profile.
6. Deploy/package/upload/canary/migrate behavior is ported, never dropped, never
   executed during the prune (it hits AWS).
7. Conventional Commit subjects only; ticket keys go in the PR title/description.

## How to work

- Streams with disjoint file ownership (A: Makefile/mk/mise, B: workflows,
  C: hygiene, D: infra). One Worktrunk worktree per stream, stacked where one
  depends on another: `wt -C <repo> switch --create <branch> --base <prev> --no-cd`.
- Commit each chunk with `wt -C <wt> step commit` (it writes the message; no `-m`).
  Never `--no-verify` / `HK=0`. Each commit builds on its own.
- Large runs: a dynamic workflow (or Gas City formula) with one agent per stream,
  then an adversarial reviewer per branch hunting for dropped behavior.

## Steps

### 0. Inventory and verdicts (read-only)

For every workflow, Makefile target, and script: trigger, what it does, commands
it calls, last 20 runs (`gh run list -R <org>/<repo> --workflow <f> -L 20`),
whether the root already covers it, and a verdict:

| Verdict   | Meaning                                          |
| --------- | ------------------------------------------------ |
| DELETE    | Fully duplicated by the root or another workflow |
| REPLACE   | Keep the intent, body becomes `mise run …`       |
| MERGE     | Fold into a sibling (matrix, input, extra job)   |
| KEEP      | Repo-specific and needed                         |
| KEEP, FIX | Needed but failing; flag for the owner           |

Before deleting a workflow, list every job: keep jobs nothing else runs
(isa-platform `proto.yml` codegen snapshot) and trim instead. Failing or dead
workflows are findings, not prune targets.

### 1. Delete retired devops

`.trunk/`, `lefthook.yml`, `renovate.json`, `.github/dependabot.yml`, prettier
configs dprint replaces, `.gate.yaml` + gate steps, per-repo bot automation,
unused composite actions, committed `__pycache__`, point-in-time audit docs. Same
commit fixes what would break (`go.work`, CI steps, allowlist lines).

### 2. Shared configs → delete the repo copy

`.editorconfig`, every `.golangci.yml`, `buf.work.yaml` (buf adapter covers it),
`pnpm-workspace.yaml` when a `link:` dep replaces its only use. Check the root
version is a superset first. Newly visible lint findings → lint-fix PR.

### 3. mise.toml → only repo-specific tasks

Delete what the root provides (setup, fmt, lint, scan, coverage, doctor, ci, tool
pins equal to the org default). Extend, don't copy:
`[tasks.test] depends = ["profile:test"]` + the repo step. Long recipes →
`mise-tasks/<group>/<name>` (bash, `set -euo pipefail`, `#MISE`/`#USAGE`
headers, shellcheck clean); shared shell → `scripts/lib/*.sh`. Never paste
fixture keys; read them from fixtures.

### 4. Stream A: Makefile → mise

Map every target (root / port / dead). Grep every caller (`make` across the
tree) → `mise run`. Workflows get `jdx/mise-action` pinned by SHA. Delete
`Makefile`, `mk/`, nested Makefiles only after every target has a task.
Sequential steps stay sequential (mise `:::` runs tasks in parallel).

### 5. Stream B: workflows (stacked on A)

- MERGE per-language workflows into one with a `changes` job (a mise task, so
  the filter is testable); gate jobs on its flags.
- Workflows only set up toolchains and `mise run`; actions pinned by SHA.
- Fold dry-run into the real workflow (input + old trigger); give folded jobs
  least-privilege `permissions:`.
- Required checks are `<workflow> / <job>`; merging renames them — list every
  rename so branch protection/rulesets change _before_ merge.
- Don't delete what's blocked (repo `ci.yml` until the profile CI is required,
  broken deploys) — list as follow-ups.

### 6. Stream C: hygiene

- Allowlist `.gitignore`: prove each `!entry` exists; slash-less `!name` matches
  at any depth, so check nested copies stay covered.
- Stale tooling mentions (trunk, lefthook, gate, pnpm, renovate) → fix.
- Root clutter / docs in `.github/workflows/` → `docs/<area>/` with `git mv`; fix
  inbound and outbound links (`rg` the names).
- Orphan tests (nothing runs them) → wire into `mise run test`.
- CODEOWNERS stays; PR template → org-level `.github` repo.

### 7. Lint-fix PR

Fix what the root config now surfaces, in code. Then flip the suppression check
from report to enforce.

### 8. Org-level (stream D)

Repo rename via infra Tofu (`fleet_repository_renames`, `moved` blocks, OIDC
subjects for both names; resources that reference the repo name must follow the
renamed resource, not a literal). Confirm in-place rename (no import/create) with
`aws-vault exec sah -- tofu -chdir=environments/github plan`. Description is not
infra-managed: `gh repo edit … --description` after the rename.

## Verify (every stream)

- `mise run ci`; `actionlint` on workflows; `shellcheck` on `mise-tasks/**`.
- Run safe tasks for real; deploy-class tasks only `bash -n` + read.
- Before/after trigger→job map: no trigger, job, or permission vanished.
- `rg` old filenames: no dangling links. Commit hooks green.

## Roll out (three steps, in order)

Prerequisite: the profile PR is merged and every machine ran
`mise bootstrap --from <profile repo> [--from-dir …] --update`.

1. Land the prune PR (all streams integrated in order, reviewed).
2. Land the reformat PR: `hk fix --all`, formatters/safe autofixers only.
3. Sync everyone: `wt sync --all --fetch`, resolve once on formatting-only
   diffs, then `wt step prune`.

## Known snags

- Git exports `GIT_DIR`/`GIT_INDEX_FILE` to hooks; a push-time test that runs
  `git init` with those set re-initializes the real repo and sets
  `core.worktree` to a worktree path — the main checkout then silently reads
  another tree. Fixed in both profiles (push contract unsets
  `git rev-parse --local-env-vars`). Check:
  `git --git-dir <repo>/.git config --get core.worktree` must be empty.
- A fix to the push hook can't push itself (the live hook is the old one):
  install the branch locally (`mise run bootstrap` in the worktree; `SAH_ROOT=…`
  for platform), push, merge, then `--update` from main.
- `go fix` is not a safe commit fixer (emitted `errors.AsType` on a non-error);
  removed from both profiles.
- `wt merge` / `wt step push` move a branch that is checked out elsewhere
  without updating that checkout's files; verify the main checkout afterwards.
- If the rendered hk config predates a hook the global git config calls, every
  commit fails (`Hook 'commit-msg' not found`): re-render the root, never skip.
- `set -e` + `wait` on a killed background server returns 143; turn errexit off
  in the EXIT-trap teardown.
- Fixture keys pasted into scripts trip gitleaks; read them from fixtures.
- mise deps auto-install only sees root lockfiles; nested packages rely on the
  node adapter's per-package `setup`.
- Use the Edit tool over `sed -i`; `trash` over `rm -rf`.
