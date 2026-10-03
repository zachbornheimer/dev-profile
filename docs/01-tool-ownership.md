# 1. Live tool inventory and ownership

Inspected 2026-10-03 on this Mac. `mise` is 2026.9.15 at `/opt/homebrew/bin/mise`. Global config is `~/.config/mise/config.toml` (chezmoi: `~/Developer/Personal/dotfiles/home/dot_config/mise/config.toml`).

## 1. mise-managed versioned tools

| Tool                     | Path / source                          | Notes                                                           |
| ------------------------ | -------------------------------------- | --------------------------------------------------------------- |
| go 1.27.1                | mise shim                              | Global `[tools]`                                                |
| govulncheck 1.8.0        | mise `go:…`                            | Global                                                          |
| hadolint latest (2.15.1) | mise                                   | Global                                                          |
| node 22 (22.23.3)        | mise shim                              | Global; `idiomatic_version_file_enable_tools = ["node"]`        |
| semgrep 1.168.0          | mise                                   | Global                                                          |
| aube                     | mise shim                              | Node package manager; preferred over npm/pnpm for agents        |
| uv                       | mise shim                              | Owns Python. Not listed in global `[tools]` but shim is on PATH |
| rustc / cargo            | mise shim                              | Per-repo (e.g. sleep-until)                                     |
| ruby                     | mise shim                              |                                                                 |
| perl                     | mise shim                              | Homebrew perl also exists; zsh local::lib uses Homebrew perl    |
| lefthook                 | mise shim                              | Also pinned per-repo                                            |
| zq                       | `~/.local/bin/zq` → mise go 1.27.1 bin | Keep installed                                                  |

## 2. Homebrew / system (bootstrap later)

`brew list --formula` returned 666 formulae. Role groups, not the dump:

- CLI daily drivers: rg, fd, tmux, zoxide, shfmt, perltidy, eza, bat, fzf, atuin, direnv, git, gh
- Worktree / local services: `wt` (Worktrunk v0.80.0), cowtree 0.4.0, caddy
- Language/system: composer (`/opt/homebrew/bin/composer`), trunk (`/opt/homebrew/bin/trunk`)
- `mise` itself is Homebrew-installed (self-update disabled)

Absent today: `dprint`, `portless`, `worktrunk` as a binary name (the CLI is `wt`).

php is `~/.local/bin/php` (not Homebrew).

## 3. Ecosystem-local package managers

Do not rebuild these. Humans and agents use `mise run …`.

| Ecosystem | Manager                                    | Evidence                                              |
| --------- | ------------------------------------------ | ----------------------------------------------------- |
| Node      | aube preferred; npm and pnpm still on PATH | zsh wrappers on npm/pnpm; aube shim                   |
| Python    | uv (`uv run`, `uv sync`, `uv tool`)        | zsh python fence; `UV_PYTHON_PREFERENCE=only-managed` |
| PHP       | Composer                                   | Homebrew composer                                     |
| Go        | native modules / `go install`              |                                                       |
| Rust      | cargo                                      | sleep-until `mise run test` = `cargo test --locked`   |
| Perl      | CPAN / local::lib                          | `$HOME/perl5`                                         |

## 4. Shell-only convenience

See artifact 2. Keep: git aliases, zoxide, atuin, fzf, opr/denv, opssh, teleport, python fence, screenshot-inbox shims. `q`/`qf`/`qa`/`qd`/`qr` are zq shortcuts in `~/.zshrc.local` — leave while zq stays.

## 5. Removable later (not this phase)

- Duplicate pyc/DS_Store cleanup aliases in `~/.zshrc.local`
- `kp` (kill-by-port) as an agent-facing habit; keep as a human shortcut until Portless/hash_port exists
- perlbrew `use-perlbrew` unless a repo still needs it
- JINA CLI block in `~/.zshrc` if unused

## Leak

Global `[env] AGENTMUX_INSTALL_STRICT = "1"` applies under Software-Automation-Holdings as well (`mise env` from `dev-config` exports it). That is one-repo policy in the base layer. Move it into agentmux's repo config in a later phase. Phase 1 does not copy it into the Personal overlay.
