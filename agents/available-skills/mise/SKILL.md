---
name: mise
description: Use when creating or modifying mise.toml, adding repo automation, setting up CI, or touching hooks, lint, or format config. The profile-driven task contract, the inheritance model, and the gotchas that break CI silently.
---

# Mise

`mise` is the sole entrypoint for every repo. CI calls `mise run ci` and nothing
else.

## The profile owns the root

Each code root has one profile (typed Pkl + mise kernel): `dev-profile` for
`~/Developer/Personal`, `platform` for `~/Developer/Software-Automation-Holdings`.
Install: `mise bootstrap --from <profile repo> --from-dir <checkout>`. It renders:

1. The code-root `mise.toml` overlay: tools, env, `[deps.*]`, contract tasks.
2. The hk config and global git hooks (`hk run pre-commit --staged` / `pre-push`).
3. Shared tool configs at the code root (`.golangci.yml`, `.editorconfig`, …).

Every repo inherits all three. Edit the profile, never its output.

## The task contract

| Task              | Purpose                                                   | Max    |
| ----------------- | --------------------------------------------------------- | ------ |
| `mise run setup`  | Install deps via mise deps providers, verify, smoke-check | 5 min  |
| `mise run build`  | Produce the deployable artifact                           | 10 min |
| `mise run lint`   | Format check + static analysis via native tools           | 2 min  |
| `mise run test`   | Run all tests                                             | 5 min  |
| `mise run scan`   | gitleaks on the tree + dependency vulnerability scanning  | 2 min  |
| `mise run doctor` | Verify the repo meets the contract                        | 30 sec |
| `mise run ci`     | lint + test + scan                                        | 15 min |

Root tasks detect ecosystems by marker file (go.mod/go.work, Node lockfile,
composer.json, pyproject/uv.lock, .NET, Gemfile, Perl, `*.tf`) and dispatch to
the native tool. Deployment is not a repo concern.

## Inheritance

- mise merges parent configs. A repo task with the same name overrides the root's.
- golangci-lint uses the first config walking up. No merging: a repo copy
  replaces the shared one.
- Repo-specific behavior goes in the repo's `mise.toml`. Copies of shared config
  don't.

## Gotchas

**A repo file needs a justification.** Copied `.golangci.yml`, `.prettierrc`,
`renovate.json`, `dependabot.yml`, or hook config diverges silently from the
profile. Delete it, or override one task in the repo's `mise.toml`.

**A check not in `ci` doesn't exist.** Run `mise run ci` locally before calling a
change done.

**Mise dispatches, it doesn't reimplement.** Tasks call `go test`, `uv run
pytest`, `composer`, etc. No inlined tool logic, no reimplemented caching.

**Commit fixes, push judges.** Commit hooks rewrite and stage, and block only on
staged secrets. Push hooks and CI block on lint, types, and security.

**No suppressions.** No inline comment may tell a linter, type checker, or
security scanner to skip code, in any tool's syntax. No config exclusions that
hide code issues either. Fix the code. A rare exception is declared once in the
profile (file + rule + ticket). Full list: the standards doc.

**No `|| true` on a check.** A check that can't fail isn't a check. Advisory
behavior is explicit and named.

**`setup` must succeed on a clean machine.** If it fails, setup has a bug.

**`.gitignore` is an allowlist.** `*` first, then `!` what belongs.

**Retired tools get removed on sight.** List: `references/retired.md`.

**A `profile:*` failure usually means a stale profile, not a bad repo.** If `mise run ci|lint|doctor|setup` fails on a `profile:*` task, `Closing comment tag`, `no-commit-to-branch` on the default branch, or `cargo fmt` disagreeing with the commit fixer, run `mise run bootstrap` in the profile checkout. Don't patch the repo. Known cases: Gotchas in the `prune-repo-devops` skill.

---

Full spec: `~/.claude/rules/devops-standards.md`
