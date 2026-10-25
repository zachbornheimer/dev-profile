# Retired tools and patterns

Remove these on sight. The profile replaced each one.

| Retired                                     | Replaced by                                                    |
| ------------------------------------------- | -------------------------------------------------------------- |
| Trunk (`.trunk/trunk.yaml`)                 | hk fixers/checks from the profile; dprint                      |
| Lefthook (`lefthook.yml`)                   | Global hk git hooks (git ≥2.54 config hooks)                   |
| semgrep                                     | gitleaks for secrets; native linters for code                  |
| Per-repo `renovate.json` / `dependabot.yml` | Profile-level Renovate runner; org Dependabot security updates |
| Makefile as task runner                     | `mise run <task>` (Make only as a real build tool)             |
| `gate`                                      | `mise run ci`                                                  |
| Managed files pulled into each repo         | Shared configs at the code root, parent-dir lookup             |
