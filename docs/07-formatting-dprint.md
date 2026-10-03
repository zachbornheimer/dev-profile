# 7. Formatting: dprint plus exec

Requirement: one command formats a Perl-heavy repo that also has Python, Go, shell, JSON, YAML, Markdown, JS, PHP.

## Decision

dprint is the common frontend **later**. Phase 1 uses each repo's existing `mise run fmt` (attention-mail: trunk + ruff). dprint is not installed today (`command -v dprint` → absent).

## Split (required by dprint security)

From dprint config docs: when using `extends`, **non-Wasm plugins in remote configuration are ignored** (they are not sandboxed). `includes` from remote configs are also ignored.

Therefore:

| Layer | Lives where | Contains |
|-------|-------------|----------|
| Shareable policy | this repo / git:: / HTTPS extends | Wasm plugins: json, markdown, toml, typescript, yaml; indent/line-width |
| Trusted exec map | local profile installed by bootstrap (`~/Developer/Personal/.dprint.json` or similar, not a remote URL) | `dprint-plugin-exec` commands: shfmt, perltidy, gofmt/gofumpt, php-cs-fixer |
| Repo override | optional `.dprint.json` `extends` + excludes | genuine local exceptions only |

Formatter **binaries** (shfmt, perltidy, …) are pinned through mise/Homebrew in the profile, not by copying configs into ~70 company repos.

## Incremental

dprint formats incrementally. Broad multi-language runs stay cheap once installed.

## Phase 1

Do not install dprint. Do not add `.dprint.json` to the SAH fleet. attention-mail `mise run fmt` is the dogfood command.
