# Improvement: replace three overlapping plugins with snacks.nvim and give the config a gate

> Historical record. Paths in it predate the grouping of `lua/zach/plugins/`
> into `ui/ editing/ coding/ git/ integrations/` (`snacks.lua` is now
> `plugins/ui/snacks.lua`). Current layout: `../LAYOUT.md`.

## Intent

Improve the Neovim configuration with [snacks.nvim](https://github.com/folke/snacks.nvim):
one plugin now owns the finder, the file explorer, `vim.ui.input`/`select`
and notifications, instead of telescope + nvim-tree + dressing, plus the
smaller snacks modules the config had no owner for (terminal, lazygit,
notifier, bigfile, quickfile).

## Goals

| ID  | Goal                                                                       | Kind        | Proof of done                                                                                             |
| --- | -------------------------------------------------------------------------- | ----------- | --------------------------------------------------------------------------------------------------------- |
| G1  | Snacks is loaded at startup with the eight used modules enabled            | behavior    | `config` scenario: `snacks is loaded at startup`, `snacks.<module> enabled`                               |
| G2  | The four finder keys keep their lhs and now drive the picker               | behavior    | `config` scenario: `keymap ,ff ,fr ,fs ,fc`, `picker opens`, `picker found the fixture`                   |
| G3  | Telescope's hand-written picker keys are redundant (already defaults)      | behavior    | `config` scenario: `picker <c-j>`, `<c-k>`, `<c-q>` read off a live picker                                |
| G4  | The explorer replaces nvim-tree and keeps the launch policy                | behavior    | `file`, `gitcommit`, `home`, `stdin`, `directory` scenarios                                               |
| G5  | Launch keeps editing focus (tree visible, cursor in code)                  | behavior    | `file` scenario: `focus stays in the editor`                                                              |
| G6  | Explorer does not reintroduce fs_event watching on Dropbox                 | invariant   | `config` scenario: `explorer does not watch the filesystem`                                               |
| G7  | `vim.ui.input`/`vim.ui.select` are owned by snacks, not dressing           | behavior    | `config` scenario: `vim.ui.input owned by snacks`, `vim.ui.select owned by snacks`                        |
| G8  | No removed plugin can be loaded or required                                | structural  | `config` scenario: `plugin telescope/nvim-tree/dressing not loaded`                                       |
| G9  | Formatting uses an API that exists in Nvim 0.12                            | correctness | `config` scenario: `vim.lsp.buf.formatting is gone in this nvim`, `LSP format path runs without a server` |
| G10 | The config has a gate that fails on the pre-change config                  | structural  | `NVIM_TEST_CONFIG=~/.config/nvim ./test/run.sh` → `gate: FAILED`                                          |
| G11 | One owner for "toggle the explorer" instead of two keymaps to two commands | structural  | `explorer.lua` is the only place that opens/closes the tree; `,T` and `,ee` call it                       |

## Hypotheses

| ID | Hypothesis                                                                    | Evidence                                                                                                                                                                                                                                                                                                                    | Verdict                                       |
| -- | ----------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------- |
| H1 | Telescope's `<C-j>`/`<C-k>`/`<C-q>` mappings duplicate picker defaults        | live picker `opts.win.input.keys` contains `<C-J>`/`<C-K>`/`<C-Q>` (uppercase after nvim normalisation)                                                                                                                                                                                                                     | confirmed                                     |
| H2 | `vim.lsp.buf.formatting()` was removed, so `F` was broken                     | `vim.lsp.buf.formatting == nil` on NVIM 0.12.6                                                                                                                                                                                                                                                                              | confirmed                                     |
| H3 | snacks `input.enabled = true` overrides `vim.ui.input` at setup               | refuted as stated: `input` is loaded on the `UIEnter` event (`snacks/init.lua` event table); headless nvim never fires it. After firing `UIEnter` the override is present                                                                                                                                                   | refuted, then confirmed with the real trigger |
| H4 | `bigfile` triggers on a 2MB buffer                                            | initially failed on a `mktemp` path because snacks compares the detected path to the buffer name and macOS `/var` is a symlink to `/private/var`; passes with a resolved fixture path                                                                                                                                       | confirmed (fixture bug, not config bug)       |
| H5 | Opening the picker steals focus from the launched file                        | `enter = false` still moves the current window (the split becomes current); without a refocus the cursor sits in the picker at +500ms                                                                                                                                                                                       | confirmed                                     |
| H6 | `on_show` is a sufficient synchronisation point for refocusing                | refocus removed → `focus stays in the editor` fails; restored → gate passes                                                                                                                                                                                                                                                 | confirmed                                     |
| H7 | `conform.nvim` and `mason-tool-installer.nvim` are installed but have no spec | refuted: `plugins/conform.lua` was created by another worker sharing this checkout while the inventory was being read, so it entered the baseline but not the inventory. `conform.nvim` is the config's formatting owner (35 filetypes from the dev-profile manifest); `mason-tool-installer.nvim` is no longer in the lock | refuted                                       |

## Pattern Inventory

| Pattern                                              |  Count | Instances                                                                               | Owner after change                                 |
| ---------------------------------------------------- | -----: | --------------------------------------------------------------------------------------- | -------------------------------------------------- |
| Finder keymaps (`<leader>f*`)                        |      4 | `plugins/telescope.lua` (deleted)                                                       | `plugins/snacks.lua`                               |
| Explorer open/toggle entrypoints                     |      3 | `core/keymaps.lua` `,T`; `plugins/nvim-tree.lua` `,ee`; nvim-tree `init` launch autocmd | `core/explorer.lua`                                |
| "Do not auto-open over special buffers" rule         |      2 | `NO_AUTO_OPEN_FILETYPES` + `buftype == "nofile"` inline checks                          | `core/explorer.lua:launch_opens_explorer`          |
| "$HOME must not mount a tree" rule                   |      1 | `plugins/nvim-tree.lua`                                                                 | `core/explorer.lua:is_home_dir`                    |
| `vim.ui.input`/`select` provider                     |      1 | `plugins/dressing.lua` (deleted)                                                        | `snacks.input` / `snacks.picker.select`            |
| fs_event watchers disabled on Dropbox paths          | 2 (+1) | `gitsigns watch_gitdir`, nvim-tree `filesystem_watchers`, `core/quit.lua` unref         | same, plus `picker.sources.explorer.watch = false` |
| Quit-time plugin watcher purge                       |      1 | `core/quit.lua:purge_plugin_watchers`                                                   | removed (plugin gone)                              |
| netrw presentation options                           |      1 | `core/options.lua:g:netrw_liststyle`                                                    | removed (`replace_netrw`)                          |
| Formatting strategy (manual `F` vs `format_on_save`) |      2 | `core/keymaps.lua` perl/go shell-outs + LSP call; `plugins/conform.lua`                 | conform (single owner); `F` delegates              |
| Headless config gate                                 |      0 | none existed                                                                            | `test/run.sh` + `test/checks.lua`                  |

## Layout

- `lua/zach/plugins/snacks.lua`: the one declaration of which snacks modules are enabled and the keymaps that call them.
- `lua/zach/core/explorer.lua`: the one owner of when the file explorer appears (launch policy, toggle, reveal).
- `test/checks.lua`: the behavior each scenario asserts, run against the real `init.lua`.
- `test/run.sh`: the gate — one nvim process per startup scenario.

Removed, each replaced by exactly one of the above: `plugins/telescope.lua`, `plugins/nvim-tree.lua`, `plugins/dressing.lua`.

## Contracts touched

| Owner                            | Contract                                                            | Behavior preserved?                                                                                          | Consumers migrated                       |
| -------------------------------- | ------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ | ---------------------------------------- |
| `,ff` `,fr` `,fs` `,fc`          | finder keymaps                                                      | yes — same lhs, same meaning                                                                                 | `plugins/snacks.lua`                     |
| `,T` / `,ee`                     | toggle file explorer                                                | yes — both still toggle, now one implementation                                                              | `core/keymaps.lua`, `plugins/snacks.lua` |
| `,E`                             | reveal current file in explorer                                     | yes (was `NvimTreeFindFileToggle`)                                                                           | `plugins/snacks.lua`                     |
| `,ec` `,er`                      | collapse / refresh explorer                                         | **no** — snacks' explorer has no equivalent; the tree collapses with `<BS>`/`Z` in-pane and refreshes itself | dropped, see Open Questions              |
| launch auto-open                 | tree visible, cursor in editor, skipped for commit/diff/stdin/$HOME | yes                                                                                                          | `core/explorer.lua`                      |
| `vim.ui.input` / `vim.ui.select` | dressing → snacks                                                   | yes                                                                                                          | `snacks.input`, `snacks.picker.select`   |
| `F`                              | format current buffer                                               | yes — and it now delegates to conform, the only owner of formatter selection, with LSP as its fallback       | `core/keymaps.lua`                       |
| `vim.notify`                     | bare nvim → snacks notifier with history                            | yes, plus `,sn` history                                                                                      | `plugins/snacks.lua`                     |

## Findings

| ID | Defect class                                                                                                                                                         | Instances | Fixed where                                                                                                       | Class prevented by                                                                                      |
| -- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------: | ----------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------- |
| F1 | Call to an API removed in Nvim 0.12 (`vim.lsp.buf.formatting`)                                                                                                       |         1 | `core/keymaps.lua`                                                                                                | `vim.lsp.buf.formatting is gone in this nvim`; `F formats through conform` asserts the replacement path |
| F2 | Same behavior owned twice (`NvimTreeToggle` behind `,T` and `,ee`)                                                                                                   |         2 | `core/explorer.lua`                                                                                               | G11: one module owns open/close; both keys call it                                                      |
| F3 | Dead code left by ownership transfer (`purge_plugin_watchers`, `quit.purge_watchers`)                                                                                |         2 | `core/quit.lua`                                                                                                   | `plugin nvim-tree not loaded`; gate loads the config                                                    |
| F4 | Option whose owner is gone (`g:netrw_liststyle`)                                                                                                                     |         1 | `core/options.lua`                                                                                                | `explorer replaces netrw`                                                                               |
| F5 | Comment naming a removed plugin                                                                                                                                      |         1 | `core/perf.lua`                                                                                                   | — (reviewed by hand)                                                                                    |
| F6 | Async picker silently steals launch focus                                                                                                                            |         1 | `core/explorer.lua` (`on_show` refocus)                                                                           | `focus stays in the editor` (red without the fix)                                                       |
| F7 | Config with no gate; failures only visible on screen                                                                                                                 |         1 | `test/`                                                                                                           | `test/run.sh` fails on the pre-change config                                                            |
| F8 | Formatting policy owned twice: `F` shelled out to `perltidy`/`go fmt` and called LSP directly, while conform decides the formatter per filetype for `format_on_save` |         2 | `core/keymaps.lua` — `F` now calls `conform.format({ lsp_format = "fallback" })`; the perl/go shell-outs are gone | `F formats through conform` spies on `conform.format`; `conform owns perl/go formatting`; red on `main` |
| F9 | Severity referred to through a member that does not exist (`vim.log.levels.error` is `nil`), so the message rendered at the default level                            |         1 | `bpp/init.lua`                                                                                                    | not mechanically guarded: a `nil` lookup is legal Lua; caught by review                                 |

## Edge cases

| ID | Condition                                        | Expected behavior                      | Test        | Red-before proof                           |
| -- | ------------------------------------------------ | -------------------------------------- | ----------- | ------------------------------------------ |
| E1 | `nvim <file>`                                    | tree opens, cursor stays in the editor | `file`      | fails without the `on_show` refocus        |
| E2 | `nvim <file>` in a git commit/rebase/diff buffer | no tree                                | `gitcommit` | fails on pre-change config only via G8/G10 |
| E3 | `nvim <file>` with cwd = `$HOME`                 | no tree                                | `home`      | —                                          |
| E4 | piped stdin (`nvim -`)                           | no tree                                | `stdin`     | —                                          |
| E5 | `nvim <dir>`                                     | tree opens instead of netrw            | `directory` | fails on pre-change config (netrw)         |
| E6 | 2MB buffer                                       | `bigfile` filetype, completion off     | `bigfile`   | fails on pre-change config                 |
| E7 | Picker opened and closed                         | no error, items delivered              | `config`    | —                                          |
| E8 | `F` with no LSP client attached                  | no error                               | `config`    | yes: `vim.lsp.buf.formatting()` is `nil`   |
| E9 | Explorer toggled closed then revealed            | closes, then reopens                   | `file`      | —                                          |

## Performance

Workload: headless startup (`nvim --headless --startuptime`, 5 runs each, best of 5).

| Config                                    | Startup |
| ----------------------------------------- | ------- |
| before (telescope + nvim-tree + dressing) | 58.4 ms |
| after (snacks, 8 modules)                 | 61.6 ms |

+3.2 ms (+5.5%) for the picker, explorer, input, notifier, bigfile, quickfile,
terminal and lazygit modules. Snacks loads eagerly because `quickfile` must run
before the plugin load and `Snacks.*` is called from keymaps; telescope and
nvim-tree were command-lazy. Interactive (TUI) startup was not measured —
`UIEnter` work is excluded from headless runs. The explorer's launch policy runs
inside `perf.span("explorer.launch")`, so its cost lands in the existing
`stdpath("log")/perf.jsonl` log.

## Verification

| Check                                | Command                                                                                  | Result                                                                                                                 | Evidence ref              |
| ------------------------------------ | ---------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------- | ------------------------- |
| Config loads with no error           | `./test/run.sh` → `load`                                                                 | ok                                                                                                                     | gate output               |
| Full gate                            | `./test/run.sh`                                                                          | `gate: passed`, 8 scenarios, 86 asserts                                                                                | gate output               |
| Gate discriminates                   | `NVIM_TEST_CONFIG=~/.config/nvim NVIM_TEST_CHECKS=$PWD/test/checks.lua ./test/run.sh`    | `gate: FAILED` (config, file, directory, bigfile)                                                                      | red-before run            |
| Focus fix is load-bearing            | remove `on_show` refocus, re-run                                                         | `FAIL focus stays in the editor`; restored → passed                                                                    | load-bearing run          |
| snacks' own diagnostics              | `:checkhealth snacks` (headless)                                                         | remaining errors are headless artifacts (no `UIEnter`, no kitty graphics); `vim.ui.input`/`select` asserted separately | health probe              |
| Lockfile matches specs               | `lazy-lock.json` diff                                                                    | +`snacks.nvim`, −telescope, −fzf-native, −nvim-tree, −dressing, −web-devicons                                          | `git diff lazy-lock.json` |
| No live reference to removed plugins | `grep -rn "telescope\|NvimTree\|nvim-tree\|dressing\|devicons\|netrw" --include=*.lua .` | only historical comments                                                                                               | grep output               |
| `F` routes to the formatting owner   | `NVIM_TEST_CONFIG=~/.config/nvim ./test/run.sh` (before fix) then after                  | `FAIL F formats through conform` on `main`, passes after the fix                                                       | red-before run            |

## NOT PROVEN

- Interactive TUI behavior: picker rendering, previews, float appearance, and
  `UIEnter`-time setup are asserted through their wiring, not through a real UI.
- The `wt merge` step and the resulting `main` state (recorded in the transcript,
  not by the gate).
- Startup cost of `UIEnter` work (picker/input setup) — headless excludes it.
- `,gg` (lazygit) and `,tt` (terminal) were asserted as keymaps only; the
  binaries exist (`lazygit` at `/opt/homebrew/bin/lazygit`) but the floats were
  not opened.

## Deviations

- The config was not a git repository, so worktrunk had nothing to branch from.
  It was `git init`-ed and a baseline commit was made before any change
  (bootstrap, since `wt switch` requires a repo); all subsequent work happened
  in the `snacks-integration` worktree.
- `.gitignore` with `.DS_Store` was added as part of tracking the config.

- The config is shared: another worker created `lua/zach/plugins/conform.lua`
  between the inventory and the baseline commit, so it is tracked but was not
  in the inventory. It was found from the formatter behaviour, not from the
  file list (H7).
