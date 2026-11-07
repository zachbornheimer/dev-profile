`apps/bat` is the `bat` pager config, tracked as `~/.config/bat`. It sets the `base16` theme and always-on italics. It maps `*.tmpl`, `*.env` and `*.envrc` to bash syntax and `Brewfile` to Ruby, so those extension-less or templated files get highlighted.

No test covers it. `config/mise.toml` is the only reference (`track`, `encrypt = true`), and a bad flag shows only when `bat` runs.
