---
name: toml-sorting-nvim
description: "Sorting or regrouping TOML (mise config.toml [dotfiles], scattered sub-tables) with taplo/tombi, and the :TomlSort command in ~/.config/nvim. Read before running taplo reorder options on any config where array order is meaning."
---

## Facts (verified 2026-11-09)

- dprint (`@dprint/toml`) has NO sort option. The nvim conform path is dprint-only and runs on save.
- `:TomlSort` / `<leader>ts` lives in `~/.config/nvim/lua/zach/core/tomlsort.lua`. Whole buffer = tombi (groups sub-tables under parent) then taplo (sorts keys per table). Range/visual = taplo only, so `[dotfiles]` sorts alone. Never on save. LAYOUT.md has the owner entry; gate checks are `check_tomlsort` in test/checks.lua.
- Neither tool merges a table written twice: duplicate `[a]` headers are invalid TOML.

## Gotchas

- **taplo picks up a `.taplo.toml` from the cwd.** One with `reorder_arrays = true` reordered `args = ["up", "x"]` in mise launchd agents and `run = [...]` hook steps, changing meaning. Always pass `--no-auto-config` plus explicit `--option reorder_keys=true --option reorder_arrays=false --option reorder_inline_tables=false`.
- **mise shims for tombi/taplo have no global version** ("No version is set for shim"). Run `mise exec taplo@0.10.0 -- taplo ...` / `mise exec tombi@0.7.27 -- tombi ...`; versions are constants in tomlsort.lua, bump on upgrade.
- tombi alone preserves parsed content and only regroups sub-tables; it does not sort keys without a schema order.
- Prove any TOML rewrite by comparing `tomllib.load` of before and after (dict equality is order-insensitive, so equal means no value changed).
- `bash ./test/run.sh` (not `./test/run.sh`, not executable). On 2026-11-09 it had 4 unrelated pre-existing FAILs: `keymap ,ee` (no such map in source) and `F` (config maps `<leader>F`).
