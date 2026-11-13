---
name: mise-docs-source
description: "Where the full mise documentation lives (source repo path, local clone, llms.txt index) and how to search it; use before researching a mise feature or when asked to load all mise docs."
---

# mise docs: where they live

Search first: `docs_search` (project `mise`, indexed 2026-11-09 from the local clone at commit 72b6f5f, 430 files, 3989 chunks) returns the matching page, heading and public URL. See skill `reuse-documented-features`. Tool files load at session start; if `docs_search` is missing, restart omp. Fall back to the clone below.

- Source: `docs/` in `jdx/mise` (VitePress). `docs/bootstrap/macos-defaults.md` becomes `https://mise.jdx.dev/bootstrap/macos-defaults.html`. CLI reference pages under `docs/cli/` are generated from the CLI spec.
- Local sparse clone: `~/Developer/Personal/mise-docs/docs` (427 Markdown files, 2.87 MB, about 700k tokens). Refresh: `git -C ~/Developer/Personal/mise-docs pull`, then `docs_index {"project":"mise","source":"~/Developer/Personal/mise-docs/docs","url_base":"https://mise.jdx.dev/","scope":"global"}` (only changed files are re-embedded).
- Index of every page with a one-line summary: `https://mise.jdx.dev/llms.txt` (70 KB, 425 entries). `llms-full.txt` and per-page `.md` URLs return 404.
- Largest sections: `dev-tools/` 518 KB, `cli/` 466 KB, `lang/` 99 KB. The whole set cannot be loaded into context.
- The index lags the project (mise's main moves daily). `docs_search` prints `stale` and the refresh call; check the changelog before saying a feature does not exist.
