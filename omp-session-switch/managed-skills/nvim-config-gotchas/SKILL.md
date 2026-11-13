---
name: nvim-config-gotchas
description: "Use when changing ~/.config/nvim (core modules, :Sort, the test gate) or running TOML/YAML/JSON formatters and sorters from it: tool versions, gate quirks, known pre-existing failures."
---

# ~/.config/nvim gotchas (verified 2026-11-09)

Layout owner: `LAYOUT.md` (one file per purpose; add a `core/*.lua` line there). Core modules are loaded from `lua/zach/core/init.lua`. `core/sort.lua` owns `:Sort` / `<leader>S` (per-filetype: toml tombi+taplo, yaml `yq sort_keys(..)`, json `jq -S`, other = LSP `source.sortImports` else `source.organizeImports`; a range = line sort or key sort for toml/yaml).

Tool facts:
- `taplo`, `tombi`, `yq` mise shims have NO global version: `taplo`/`tombi`/`yq` fail with "No version is set for shim". Use `mise exec taplo@0.10.0 -- ...`, `tombi@0.7.27`, `aqua:mikefarah/yq@4.49.2`. `jq` shim works bare. Bump the constants at the top of `core/sort.lua` when upgrading.
- `dprint` (the save-time formatter via conform) has NO sort option for toml/yaml. `@dprint/toml` and `dprint-plugin-yaml` format only.
- taplo `reorder_arrays=true` scrambles argv-style arrays (`args = ["up", "x"]` -> `["x", "up"]`) and a cwd `.taplo.toml` can switch it on: always pass `--no-auto-config` plus explicit `--option reorder_arrays=false --option reorder_inline_tables=false`.
- Neither taplo (no code-action support) nor tombi (returns none) LSP offers a sort code action. ts_ls advertises `source.sortImports.ts` and `source.organizeImports.ts` (suffixed kinds: match by prefix, not equality); gopls only organizeImports (also adds/drops imports). yq (no `-P`) keeps comments attached to keys and flow style.
- Two `tombi format` runs plus taplo preserved parsed content on the real mise `config.toml` (tomllib equality) and all comments.

Gate (`test/run.sh`):
- Not executable: run `bash ./test/run.sh` (takes ~60s+, promoted to background; read its log).
- Output is one long line; split the log on `PASS`/`FAIL` to read it.
- Four checks fail on a clean tree and are NOT regressions: `keymap ,ee`, `space leader ee`, `F is mapped`, `F formats through conform` (the config maps `<leader>F`, and no `,ee` exists). Judge your change by its own checks.
- Scratch buffers in tests must pass the filetype explicitly to `sort_buffer(buf, first, last, ft)`; setting `vim.bo.filetype` fires the LSP FileType autocmd and starts/downloads servers inside the gate.
- The directory is not a git repo; there is no `git status`/stash to compare against.

Real-LSP check recipe: `nvim --headless -u NONE -l probe.lua` with `package.path` pointing at `~/.config/nvim/lua`, start the server from `~/.local/share/nvim/mason/bin/` with `vim.lsp.start`, wait for `client.initialized`, call the module, print buffer lines before/after.
