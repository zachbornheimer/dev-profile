---
name: nvim-finder-perf-mise-shims
description: "Profiling or fixing slowness of Zach's nvim finders (snacks picker grep/files, rg/fd, \"LeaderF\"-style search): mise shim cost, live config location, herdr pane grep alias, how to run the gate."
---

# Nvim finder performance (Zach's machine)

- **Live config is `~/.config/nvim`** (plain dir, dotfile-synced). `~/Developer/Personal/dev-env/nvim/` is an older diverged copy. Edit the live one; other agents edit it concurrently, so re-read before each `edit`.
- **Finders are snacks.nvim**, not LeaderF/telescope. `<leader>fs`/`fc` = `rg` grep (title says "Grep"), `<leader>ff` = `fd`. Leader is `,` (and space). Snacks spawns `rg`/`fd` by bare name; live grep spawns one per keystroke.
- **Perf trap: mise shims** (`~/.local/share/mise/shims/{rg,fd,nvim}`) are first on PATH; each spawn runs a full `mise` startup (seconds to ~1 min under load vs 4 ms for real `rg`). Fix lives in `core/finder_bin.lua`: symlink real rg/fd into `stdpath("state")/finder-bin`, prepend to nvim's PATH. Do not prepend /opt/homebrew/bin wholesale (changes node/python resolution). When launching nvim yourself use `/opt/homebrew/bin/nvim` or `PATH=/opt/homebrew/bin:$PATH`.
- `ug` ~5 ms faster than `rg` on a 300-file repo (startup-dominated), but snacks parses rg-specific flags; keep rg. System `grep -r` ~600x slower.
- **Herdr pane shells alias `grep` to `rg`**: `| grep -E` fails there; use `command grep` or `/usr/bin/grep`.
- hyperfine is at `~/.local/share/mise/installs/hyperfine/2.0.0/hyperfine-v2.0.0-aarch64-apple-darwin/hyperfine` (not on PATH); use `-N` for spawn timing.
- Gate: `PATH=/opt/homebrew/bin:$PATH bash ~/.config/nvim/test/run.sh` (not executable; takes minutes). Unrelated failures as of 2026-11-09: `,ee` keymap (now `<leader>t`), `F`/conform, HerdrNvimComment contrast.
- `~/.config/mise/config.toml:361` has a duplicate `"~/.ssh/config"` key; every mise run prints a parse error.
