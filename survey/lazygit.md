`apps/lazygit` is `config.yml` for lazygit, tracked as `~/.config/lazygit`. It uses `delta --dark --paging=never` as the diff pager with colors forced on, shows the file tree, selects Nerd Fonts version 3 glyphs, and makes the active border green and bold.

No test exercises it. `config/mise.toml` is the only reference (`track`, `encrypt = true`). The yamllint step in `hk/hk.pkl` (`yamllint --strict`) is the one automated check that applies to the file.
