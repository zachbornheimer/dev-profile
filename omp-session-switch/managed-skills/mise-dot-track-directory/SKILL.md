---
name: mise-dot-track-directory
description: "Sync a directory (e.g. ~/.omp/agent/tools) across machines with mise dot instead of git branches: track it encrypted, exclude node_modules, verify the file count."
---

Use when a local-only directory of files (omp custom tools, scripts) needs cross-machine sync and no upstream repo wants it.

1. Preview: `mise dot track --dry-run <dir>`. It prints file count, size, and `omitted:` lines. Credential-looking files (e.g. `credentials.ts`) are refused unless the entry is encrypted.
2. Track: `mise dot track --encrypt <dir>`. This writes an entry in `~/.config/mise/config.toml` (the live config is the tracked source; edit it directly) and saves a baseline checkpoint. Large dirs take more than 20 s, so run it in the background.
3. Exclude heavy generated content by editing the entry:
   `"~/.omp/agent/tools" = { mode = "track", encrypt = true, exclude = ["**/node_modules/**"] }`
   Per-entry `exclude` is the right place; `mise dot exclude <glob>` is global.
4. Verify: `mise dot track --dry-run <dir>` again. For `~/.omp/agent/tools` the count went 3,162 files / 115 MiB to 2,125 files / 12.6 MiB. Then `mise dot history | head` for a new checkpoint.

Notes:
- `mise dot save` can fail with "another history operation is running" while the watcher is saving. Retry later; the watcher autosaves.
- node_modules is not synced, so a new machine needs `bun install` in tool dirs that have a package.json.
- Do not use `mise dot` for the fork's `.omp-build/branches/*.toml` carry list; that lives in git on fork `main`.
