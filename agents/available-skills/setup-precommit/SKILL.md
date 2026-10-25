---
name: setup-precommit
description: Use only when user explicitly asks for pre-commit or the repo already uses it. Default is mise + Trunk + Lefthook — prefer that unless pre-commit is specifically requested.
user-invokable: true
disable-model-invocation: true
argument-hint: "[path-to-repo]"
allowed-tools: mcp__capability__agentmux_capability_run_command Read Write Edit Glob Grep
---

# Setup Pre-commit

Legacy skill for explicit pre-commit requests only. The default repo policy is:

- `mise` owns toolchains and task orchestration.
- Trunk owns repo linting, formatting, and secrets checks.
- Lefthook owns Git hooks and delegates to `mise run` tasks.

Do not create `.pre-commit-config.yaml` for a normal repo setup. Use this skill only when the user explicitly asks for pre-commit, when maintaining a repo that already standardizes on pre-commit, or when compatibility with an existing pre-commit workflow is a concrete requirement.

## Step 1: Read the spec

Read `~/.claude/rules/devops-standards.md` first. It is the source of truth for the mise task contract, Trunk configuration, and Lefthook hooks. If the request is actually a generic "set up linting/hooks" request, configure those instead of pre-commit.

If the user explicitly requested pre-commit, continue with the compatibility workflow below.

## Step 2: Detect languages

Scan for file extensions AND manifest files:

- `*.go` → Go (gofmt, goimports, go-vet, golangci-lint)
- `*.ts`, `*.tsx`, `*.js`, `*.jsx` → TypeScript/JS (prettier, eslint)
- `*.php` → PHP (php-cs-fixer, phpstan)
- `*.py` → Python (ruff format, ruff check)
- `*.pl`, `*.pm` → Perl (perltidy, perlcritic)
- `*.swift` → Swift (swiftformat, swiftlint)
- `*.rs` → Rust (rustfmt, clippy)
- `*.sh`, `*.bash` → Shell (shellcheck, shfmt)
- `*.sql` → SQL (sqlfluff)
- `*.css`, `*.scss` → CSS (stylelint)
- `Dockerfile` → Docker (hadolint)
- `*.tf` → Terraform (terraform fmt, tflint)
- `*.yaml`, `*.yml` → YAML validation

## Step 3: Create or update

**If no `.pre-commit-config.yaml` exists**, create from scratch:

Always include these universal hooks:

```yaml
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-json
      - id: check-added-large-files
      - id: check-merge-conflict
      - id: detect-private-key

  - repo: https://github.com/commitizen-tools/commitizen
    hooks:
      - id: commitizen
        stages: [commit-msg]

  - repo: https://github.com/gitleaks/gitleaks
    hooks:
      - id: gitleaks
```

Then add per-language hooks from the devops-standards spec.

**If `.pre-commit-config.yaml` exists**, parse it. For each detected language, check if the required hooks are already present (match by hook ID). Add only missing hooks. Do NOT modify existing hook configs. Do NOT duplicate.

## Step 4: Install

Run:

```bash
pre-commit install --hook-type pre-commit --hook-type commit-msg
```

## Step 5: Validate

Run `pre-commit run --all-files` to verify hooks work. Also report that this is a legacy compatibility path and identify the preferred `mise`/Trunk/Lefthook migration if appropriate.

## Reference

There is no default pre-commit reference implementation. For normal repo automation, use `mise.toml`, `.trunk/trunk.yaml`, and `lefthook.yml` per `~/.claude/rules/devops-standards.md`.
