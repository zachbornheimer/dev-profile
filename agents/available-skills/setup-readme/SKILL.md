---
name: setup-readme
description: Use when user says 'set up readme', 'create readme', or 'improve readme' — detects project type, extracts mise tasks, documents Trunk and Lefthook, generates architecture section.
user-invokable: true
disable-model-invocation: true
argument-hint: "[path-to-repo]"
allowed-tools: mcp__capability__agentmux_capability_run_command Read Write Edit Glob Grep
---

# Setup README

Create or enhance a README.md with standard sections.

## Step 1: Gather project context

- Read `mise.toml` to extract available tasks; read `Makefile` only when Make is the repo's actual build tool or documented user-facing interface
- Check `.trunk/trunk.yaml` for lint, format, and secrets tooling
- Check `lefthook.yml` for Git hooks that delegate to `mise run` tasks
- Detect language(s) from manifest files (go.mod, package.json, composer.json, etc.)
- Read the manifest for project name and description
- Check for `docs/adr/` directory
- Check for `LICENSE` file
- Check for `CONTRIBUTING.md`
- Scan entry point files (`cmd/*/main.go`, `src/index.ts`, etc.) for architecture overview

## Step 2: Create or enhance

**If no README.md exists**, generate with these sections:

```markdown
# Project Name

Brief 2-3 sentence description.

## Build & Test

(derived from `mise.toml` — use exact `mise run` commands; use `make` only for repos where Make is the actual build tool or ecosystem-standard interface)

## How It Works

(high-level architecture: entry points, data flow, key abstractions)

## Environment Variables

(scan for os.Getenv / process.env / equivalent — table format)

## Architecture

(directory structure with 1-line purpose for each dir)

## Contributing

(conventional commits, Lefthook hooks, `mise run ci` before PR)

## License

(from LICENSE file)
```

**If README.md exists**, read it and identify which standard sections are missing. Offer to add missing sections. Don't overwrite existing content — enhance only.

## Step 3: Quality check

Verify:

- README is non-empty
- Build instructions reference actual `mise.toml` tasks, or actual Makefile targets only when Make is the repo's real build interface
- Environment variables table is accurate (cross-check with code)
- Architecture section matches actual directory structure
