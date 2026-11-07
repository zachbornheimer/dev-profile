`apps/direnv` holds `direnvrc`, which defines one custom layout, `layout_uv`. When a project's `.envrc` calls it, the function creates `.venv` with `uv venv` if the directory is missing, adds `.venv/bin` to `PATH` with `PATH_add`, and exports `VIRTUAL_ENV`. It is tracked as `~/.config/direnv`.

There is no test for it. `config/mise.toml` is the only reference (`track`, `encrypt = true`), and the repo-wide shell linters see it as bash. The function is exercised only when direnv loads an `.envrc` that uses `layout uv`.
