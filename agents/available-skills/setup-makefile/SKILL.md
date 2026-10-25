---
name: setup-makefile
description: "Legacy skill for explicit Makefile requests only. Default policy is the code-root profile: mise for task orchestration, profile-rendered hk for hooks, lint, format, and secrets. Use Make only when the user explicitly asks for it or the repo's actual build tool/ecosystem-standard interface is Make."
user-invokable: true
disable-model-invocation: true
argument-hint: "[path-to-repo]"
allowed-tools: mcp__capability__agentmux_capability_run_command Read Write Edit Glob Grep
---

# Setup Makefile

Legacy skill for explicit Makefile requests only. The default repo policy is:

- The code-root profile renders the root `mise.toml` overlay, the hk config, and global git hooks. Repos inherit them.
- `mise` owns toolchains and task orchestration.
- hk owns linting, formatting, and secrets checks. Repos carry no hook config.

Do not create a Makefile as the default task runner. Use this skill only when the user explicitly asks for Make, when Make is the repo's actual build tool, or when Make is the ecosystem-standard interface for that project.

## Step 1: Determine target

If an argument was provided, `cd` to that directory. Otherwise use the current working directory. Verify it is a git repository.

## Step 2: Ownership check

Run `gh repo view --json nameWithOwner,viewerPermission 2>/dev/null` to verify push access. If the command fails (no remote, not GitHub), warn the user but proceed — local-only repos are fine. If `viewerPermission` is `READ`, refuse to modify and explain why.

## Step 3: Detect language(s)

Check for manifest files in this order:

- `go.mod` → Go (`go build`, `golangci-lint`, `go test`)
- `package.json` → Node/TypeScript (`npm run`, `eslint`, `jest`/`vitest`)
- `composer.json` → PHP (`composer`, `phpstan`, `phpunit`)
- `pyproject.toml` or `setup.py` → Python (`ruff`, `pytest`)
- `Cargo.toml` → Rust (`cargo build`, `cargo clippy`, `cargo test`)
- `Package.swift` → Swift (`swift build`, `swiftlint`, `swift test`)
- `Gemfile` → Ruby (`bundle exec`, `rubocop`, `rspec`)

Multiple languages can coexist (monorepo). Report all detected.

## Step 4: Read the spec

Read `~/.claude/rules/devops-standards.md` for the complete mise task contract and the limited cases where Make is appropriate. This is the source of truth for required tasks and their semantics.

## Step 5: Create or audit

If Make is not explicitly required, override only the repo-specific tasks in the repo's `mise.toml` per `devops-standards.md`. The root overlay supplies the rest.

**If no Makefile exists and Make is appropriate:** Generate one that delegates to the repo's real build interface and does not compete with `mise`. Prefer `mise run <task>` documentation unless Make is the user-facing interface. Required task semantics are:

- `setup` — install deps (mise deps providers), verify environment
- `build` — produce deployable artifact
- `lint` — static analysis and formatting checks
- `test` — run all tests (with race detection for Go)
- `scan` — gitleaks on the tree + dependency vulnerability scanning
- `doctor` — verify the repo exposes the standard contract
- `ci` — lint + test + scan (the full gate)

Each target calls the ecosystem's native tool or delegates to `mise run <task>`. Make must not reimplement the build system or become the default orchestrator unless Make is the repo's actual build interface.

**If Makefile exists:** Audit it against the contract. Report:

- Missing targets
- Targets that reimplement instead of orchestrating
- `ci` target that doesn't call all three sub-targets (lint, test, scan)
- Missing `.PHONY` declarations

Offer to add missing targets without modifying existing ones.

## Step 6: Validate

Run `make -n ci` (dry run) when Make is the requested interface. Otherwise run `mise run ci`.

## Reference

For new or generic repo automation, the profile-rendered root `mise.toml` plus hk is the reference implementation. Existing Makefiles are compatibility surfaces unless Make is the actual build tool.
