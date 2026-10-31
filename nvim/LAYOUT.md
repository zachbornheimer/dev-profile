# Layout

One file, one purpose. To change X, open the file named for X.

```
init.lua                  perf hooks -> core -> lazy
lua/zach/
  lazy.lua                bootstraps lazy.nvim, imports the five plugin groups
  core/                   no plugins: options, keymaps, quit, perf, explorer launch policy, filetype, appearance, contrast
  plugins/<group>/*.lua   one lazy.nvim spec per plugin (or tightly coupled set)
  bpp/                    project-specific commands
test/run.sh, checks.lua   the gate (see below)
docs/                     historical change records
```

## Plugin groups (`lua/zach/plugins/`)

| Group           | Holds                    | Specs                                                                                                                                |
| --------------- | ------------------------ | ------------------------------------------------------------------------------------------------------------------------------------ |
| `ui/`           | what you look at         | `colorscheme`, `which-key`, `render-markdown`, `snacks` (picker, explorer, input, notifier, terminal, lazygit), `fine-cmdline` (`;`) |
| `editing/`      | moving and changing text | `flash`, `mini` (surround, ai), `better-escape` (`kj`), `quicker` (quickfix), `gx` (open links), `persistence`, `alternate-toggler`  |
| `coding/`       | language support         | `blink` (completion), `copilot`, `treesitter`, `mason` (LSP), `conform` (formatting), `trouble`, `godotdev`                          |
| `git/`          | version control          | `git` (gitsigns, fugitive, diffview), `conflict` (git-conflict)                                                                      |
| `integrations/` | other programs           | `herdr` (herdr-nvim annotations), `kitty-scrollback`, `markdown-preview`                                                             |

Add a plugin: create `plugins/<group>/<name>.lua` returning a spec. No other
file needs to change. A new group needs one `{ import = ... }` line in `lazy.lua`.

## Owners

- `ui/snacks.lua`: which snacks modules are enabled, plus the finder, terminal,
  lazygit and notification keymaps.
- `ui/colorscheme.lua`: Rosé Pine Dawn under macOS light, Moon under dark,
  matching kitty's auto themes. `core/appearance.lua` reads macOS and is
  rechecked on focus. The background is opaque on purpose: a transparent one
  lets the desktop behind kitty set the contrast.
- `core/contrast.lua`: after every colorscheme load, raises any text group
  under 4.5:1 against its background, and the cursor against every
  background it can sit on. Decoration (indent guides, borders, staged git
  signs) is exempt. The gate's `colors` scenario checks both appearances.
- `core/keymaps.lua`: `<leader>D` asks before trashing the current file. No and
  Esc dismiss the prompt. Yes runs `trash` and leaves the window open; that
  window's statusline says `Successfully trashed` plus the absolute path.
- `core/undo.lua`: persistent undo in `~/.VIM_UNDO_FILES`. History written
  before a path became a symlink is copied onto the resolved name when the
  file still matches, so `u` finds it. A mismatch is parked, not applied
  (`:UndoArchive`); replaying it would corrupt the buffer.
- `core/explorer.lua`: when the file explorer appears (launch policy, toggle,
  reveal). Keymaps and specs route here.
- `coding/conform.lua`: the one formatter policy. `F` calls it.
- `core/filetype.lua`: `NVIM_FILETYPE` sets the syntax for this launch. A
  `#!/usr/bin/env -S uv run --script` file with a PEP 723 block is Python
  (`learn-launch`), not conf.
- `core/quit.lua`: nothing may block quit on fs watchers (Dropbox). Plugins that
  stop an `fs_event` in `VimLeavePre` get that hook removed in their spec
  (`git/conflict.lua`, as gitsigns does in `quit.lua`).
- `editing/better-escape.lua` owns leaving insert mode with `kj`. It supports
  two-key shortcuts only.
- `editing/quicker.lua` owns the quickfix buffer; `<leader>qq` / `<leader>qo`
  toggle it. `<leader>q` is shared with persistence
  (`qs ql qd`): check both before adding a key.
- `ui/fine-cmdline.lua`: `;` opens the floating command line. `:` stays native.
- `git/conflict.lua`: conflict keys are `<leader>m` + `o t b 0`, `]x`/`[x`.
  The plugin defaults (`co ct cb c0`) shadow real `c` commands.
- `integrations/herdr.lua`: annotation keys `<leader>a*`, loaded only when
  `HERDR_ENV` is set. The sidebar and file picker are a herdr plugin
  (`herdr plugin install ChmaraX/herdr-nvim`), bound to `prefix+e` / `prefix+o`
  in `~/.config/herdr/config.toml`.

## Gate

```sh
./test/run.sh        # one headless nvim per scenario; prints `gate: passed`
```

Scenarios: `load config file gitcommit directory bigfile home plugins no-herdr stdin`.
`plugins` runs against a real unmerged git repo and exercises git-conflict,
better-escape, gx, quicker, fine-cmdline and herdr-nvim. `no-herdr` proves
herdr-nvim stays out of a nvim started outside a herdr pane.

## Removed

- `telescope`, `nvim-tree`, `dressing` -> snacks (`docs/snacks-migration.md`)
- `lkj` and `;`-as-`:` insert/normal maps -> better-escape and fine-cmdline
