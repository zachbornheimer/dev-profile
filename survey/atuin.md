`apps/atuin` is a five-line `config.toml` for the atuin shell-history tool, tracked as `~/.config/atuin`. It sets fuzzy search, global filter mode, `enter_accept = true` (Enter runs the selected command), a preview pane, and `sync_frequency = "0"`. That last value means sync is attempted on every command, not turned off.

It has no tests. `config/mise.toml` is the only reference (`track`, `encrypt = true`), and any validation is atuin's own parse at startup.
