Harness auto-scan exposes only `typesafe-ai` (`~/.agents/skills/typesafe-ai`). Everything else lives here, a sibling of `skills/`, never a child. The TypeSafe picker still lists this directory in its roster roots. Do not nest this folder under `skills/`; a recursive scan would walk it.

- omp: reads `~/.agents/skills`; `available-skills` is outside the scan.
- Codex desktop: `~/.codex/skills/typesafe-ai` plus vendor `.system`.
- Claude Code, OpenCode, Grok Build, Cursor and Hermes are removed and unsupported; nothing links skills for them.
