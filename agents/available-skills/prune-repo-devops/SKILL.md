---
name: prune-repo-devops
description: Use when a repo's own devops (hooks, linters, formatters, task runners, CI, scripts, configs) might duplicate what the profile provides, or the user wants a repo on the Zach devops approach. Read this BEFORE answering or editing, not after. Triggers include prune, clean up, slim down, migrate or onboard a repo to the profile (dev-profile / platform); "can we delete/remove X from this repo" for any config, script, workflow, or hook (.golangci.yml, renovate.json, lefthook, trunk, husky, pre-commit, Makefile, scripts/, workflows); a mise.toml that copies setup/lint/test/ci instead of `depends = ["profile:<verb>"]`; any `mise run` failure that mentions `profile:ci`, `profile:lint`, `profile:test`, dev-profile-contract, no-commit-to-branch, "Closing comment tag", or a stale profile; scaffolding a new repo or a PR that adds devops files. Load it alongside `mise` for those errors. To author new mise tasks use `mise`; this skill decides what a repo keeps, deletes, or extends.
---

# Prune Repo Devops

Run `scripts/inventory.sh [repo]` first. It lists every devops artifact with a verdict hint
(DELETE-RETIRED, DELETE-ROOT-COVERS, REPLACE-WITH-MISE, KEEP-REVIEW, EXTEND-PROFILE).

## The one question

For every workflow, config, script, task, hook, pin, or doc: can this leave the repo?
Move to the profile if shared, delete if the root duplicates it, or keep it as a repo
task that extends `profile:<verb>`. Profile bugs are fixed in the profile, never per repo.

## Rules that decide every file

1. Automation lives once, in the profile. Per-repo copies are the defect.
2. mise is the only entrypoint. No Makefile runner; no task runs `make`.
3. Python only through uv. 4. Node through aube.
4. No `|| true` on a check, no inline suppressions. Exceptions live in the profile.
5. Deploy/package/migrate behavior is ported, never dropped, never run during a prune.
6. Conventional Commit subjects; ticket keys go in the PR.

## Steps (detail: `references/prune-playbook.md`)

| # | Step                                                                       | Result          |
| - | -------------------------------------------------------------------------- | --------------- |
| 0 | Inventory + verdict per artifact                                           | read-only table |
| 1 | Delete retired devops (.trunk, lefthook, renovate, dependabot, .gate.yaml) | commit          |
| 2 | Delete shared-config copies (.editorconfig, .golangci.yml, buf.work)       | commit          |
| 3 | mise.toml keeps only repo tasks that extend `profile:<verb>`               | commit          |
| 4 | Makefile/mk to mise tasks, update every caller                             | commit          |
| 5 | Workflows merged, SHA-pinned, `mise run` only                              | commit          |
| 6 | Hygiene: allowlist .gitignore, stale mentions, orphan tests                | commit          |
| 7 | Lint-fix PR, then enforce suppression check                                | PR              |
| 8 | Org-level (rename, rulesets)                                               | infra PR        |

Verify with `mise run ci`. Run safe tasks for real. Never execute deploy-class tasks.

## Gotchas

- No Rust adapter in the profile: Rust repos keep `lint`, `test`, `build` as repo tasks with `depends = ["profile:<verb>"]` plus the cargo step. Do not redefine `setup`, `scan`, `ci`. Drop `typecheck` when clippy over all targets covers it.
- Do not redefine `ci`: `profile:ci` runs lint, test, scan through the repo overrides.
- Repo-specific doctor checks go in `mise-tasks/<group>/<name>`; `doctor` becomes `depends = ["profile:doctor", "<group>:<name>"]`. Delete scripts/doctor.sh and scripts/scan.sh (the profile adapter runs gitleaks on the tracked tree).
- Hooks are global (hk). Lefthook installed means double hooks: check `.git/hooks` for lefthook files; remove lefthook.yml, its mise `[tools]` pin, the setup `lefthook install` step, and tool lists in scripts/doctor.
- Commit with `wt step commit` (no -m). Plain `git commit`, `git add -A`, `git stash`, `git restore`, `git merge` are blocked by guard hooks. Integrate with `wt merge --no-squash --no-remove` from the branch worktree.
- `wt merge` auto-commits untracked files. Clear strays first; a `target` symlink slipped in because `.gitignore` had `target/` (trailing slash does not match a symlink). Use `target`.
- `wt merge` refuses to fast-forward over uncommitted edits in the main checkout. Clear it first (the user runs stash/restore with `!` when a hook blocks).
- Bare `rustfmt` assumes edition 2015 and fights `cargo fmt`. `dev-profile-rustfmt` passes the edition (dev-profile PR 16). If format and `cargo fmt --check` disagree, the profile is stale: `mise run bootstrap` in the profile checkout, never edit the repo.
- `mise run lint` on the default branch failing on `no-commit-to-branch` means a stale profile (fixed by the `lint` hk profile, PR 16).
- `profile:ci` error `Closing comment tag '#}' not found`: a profile task script contained `${#arr[@]}` (Tera comment opener). Fix in the profile, never in the repo.
- cargo-deny needs the rendered `~/Developer/Personal/deny.toml`; no repo `deny.toml` copy.
- After a profile fix (own worktree, then `wt pr`), run `mise run bootstrap` in the profile checkout (local form, not `--from`, which clones the remote).
- Other snags (GIT_DIR in hooks, push-hook self-fix, `wait` exit 143): playbook "Known snags".

See also: `mise` skill (task authoring, contract) and `~/.claude/rules/devops-standards.md`.
