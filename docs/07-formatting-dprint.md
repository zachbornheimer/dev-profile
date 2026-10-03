# 7. Formatting: dprint plus exec

Requirement: one command formats a Perl-heavy repo that also has Python, Go, shell, JSON, YAML, Markdown, JS, PHP.

## Decision

dprint is the Personal frontend. The overlay pins it (`[tools] dprint = "latest"`). Parent `[tasks.fmt]` uses `dir = "{{cwd}}"` so `mise run fmt` in a Personal repo formats that repo. This repo's `mise run fmt` is `dprint fmt`. attention-mail keeps trunk + ruff; do not run `dprint fmt` there.

## Split (required by dprint security)

From dprint config docs: when using `extends`, **non-Wasm plugins in remote configuration are ignored** (they are not sandboxed). `includes` from remote configs are also ignored.

Therefore:

| Layer            | Lives where                                                           | Contains                                                                                               |
| ---------------- | --------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| Shareable Wasm   | `format/personal.jsonc` copied to `~/Developer/Personal/dprint.jsonc` | typescript, json, markdown, toml, dockerfile, yaml, ruff, gofumpt, mago, kachick/sh                    |
| Trusted exec map | same local file (not a remote URL)                                    | `npm:@dprint/exec` checksum from `dprint add exec`: perltidy (`pl`/`pm`/`t`), `terraform fmt -` (`tf`) |
| Repo override    | optional `.dprint.json` `extends` + excludes                          | genuine local exceptions only                                                                          |

Ancestor discovery finds `~/Developer/Personal/dprint.jsonc` from any Personal checkout. Shell uses the kachick/sh Wasm plugin (`dprint add npm:@kachick/dprint-plugin-sh`), not exec.

Formatter **binaries** for exec (perltidy, terraform) stay on PATH via Homebrew/mise. Do not copy dprint config into ~70 company repos.

## Incremental

dprint formats incrementally. Broad multi-language runs stay cheap.

## Dogfood

`dprint fmt` / `dprint check` only inside this repo. attention-mail `mise run fmt` is unchanged.
