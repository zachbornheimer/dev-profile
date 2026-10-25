Audit this project against all standards in ~/.claude/rules/ and fix it.

Work through this in order. Complete each step before moving to the next.

1. **Makefile contract.** Does a Makefile exist with all required targets (setup, build, lint, test, fmt, ci, audit, clean, coverage)? If not, create or fix it. The Makefile must call the ecosystem's native tools, not reimplement them.

2. **File structure.** Does the directory layout read as a table of contents? Are there files in root that don't belong? Is .gitignore an allowlist? Fix what's wrong.

3. **Standards docs.** Does `docs/standards/` exist? Does `docs/adr/` exist with at least one ADR? Does `docs/runbooks/` exist? Create what's missing.

4. **README.** Does it explain what this is, how to set it up, and how to run it? Fix it if not.

5. **Pre-commit.** Is `.pre-commit-config.yaml` present and pointing to the shared hooks repo? If not, add it.

6. **Code quality.** Scan every source file. Flag files over 250 lines, functions over 50 lines, direct system calls that should be facades, bare error returns, magic numbers, names that expose implementation. Fix the highest-priority issues. Create issues for the rest.

7. **Tests.** Are tests present? Do test names describe behavior? Are there obvious gaps in coverage? Flag what's missing.

8. **Observability.** If this is a service: are there health/ready endpoints? Is structured logging in place? Is there any OTel instrumentation? Flag what's missing.

9. **Summary.** List what you fixed, what you flagged, and what still needs manual attention.

Do NOT try to fix everything at once. Fix the structural issues (steps 1-5) first, commit those, then address code quality (steps 6-8) in separate commits. Keep diffs small and focused.
