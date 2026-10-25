Harness auto-scan exposes only `typesafe-ai` (`~/.agents/skills/typesafe-ai`, plus the
Grok copy at `~/.grok/skills/typesafe-ai`). Everything else lives here — a sibling of
`skills/`, never a child. The TypeSafe picker still lists this directory in its roster
roots. Do not nest this folder under `skills/`; Grok walks that tree recursively.

- Grok: scans `.agents/skills` + `.grok/skills`; `[compat.cursor]` / `[compat.claude]`
  `skills=false`; `[skills] ignore` covers `available-skills` and leftover `synced`
- Claude / OpenCode: the only per-skill link in `~/.claude/skills` is `typesafe-ai`;
  plugin `synced` is relocated by the SessionStart hook
- Codex: `~/.codex/skills/typesafe-ai` plus vendor `.system`
- Cursor: only a `typesafe-ai` symlink; extras load via the picker or by path
