`apps/ripgrep` is a five-line `config` for ripgrep, tracked as `~/.config/ripgrep` (ripgrep reads it through `RIPGREP_CONFIG_PATH`). It turns on smart-case matching, searches hidden files, and excludes `.git`, `.DS_Store` and `node_modules` by glob.

It has no test. `config/mise.toml` is the only reference (`track`, `encrypt = true`). `shell/zsh/05-env.zsh` exports `RIPGREP_CONFIG_PATH="$HOME/.config/ripgrep/config"`, which is what makes ripgrep read it.
