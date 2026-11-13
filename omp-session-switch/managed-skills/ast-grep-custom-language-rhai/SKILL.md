---
name: ast-grep-custom-language-rhai
description: "Use when ast-grep/ast_grep/ast_edit says a language (rhai, perl) \"is not supported\", or when adding a tree-sitter grammar to ast-grep on this fleet (Mac, VPS boxes, e2b containers)."
---

## Facts (measured 2026-11-09, ast-grep 0.51.1)
- ast-grep ignores native custom grammars unless the call has `--custom-languages allow`. `trust` needs an interactive tty, so it cannot be automated. Env var `AST_GREP_TRUST_DIR` only relocates the trust store.
- The grammar registry (`sgconfig.yml` with `customLanguages`) is found only by walking up from cwd, or via `--config`. `~/.config/ast-grep/sgconfig.yml` (the tracked perl one) is NOT read by plain calls and is inert.
- Rhai is supported via NotAShelf/tree-sitter-rhai pinned at 6003176 (parser.c + scanner.c, ABI 15), compiled with `cc -shared -fPIC`.

## Where it lives (dev-env main)
- `tools/ast-grep/setup.sh`: builds `~/.local/share/dev-env/ast-grep/grammars/rhai.{dylib,so}`, writes `sgconfig.yml` (absolute libraryPath), installs the launcher `~/.local/bin/ast-grep` (`launcher.sh`). Idempotent; run by the `bootstrap` task in dev-env `mise.toml` and by a line in the `final` hook of `~/.config/mise/config.toml` (the global config boxes adopt).
- Launcher adds `--config <registry> --custom-languages allow` to `run`/default calls, unless scan/test/new/lsp/outline, explicit --config/--custom-languages, or a project sgconfig.yml exists above cwd. `sg` is not wrapped.
- capability-replicas `packages/ai/src/tools/ast/ports.ts` `astGrepEnvironment()` puts `~/.local/bin` first on the engine's PATH when the launcher exists. Reason: the gateway PATH has mise shims before ~/.local/bin, and mise-activated shells put the tool install dir first, so PATH order alone is unreliable.
- Proof: `mise run test:ast-grep-rhai` (tests/ast_grep_rhai.sh; needs network, cc, ast-grep).

## Gotchas
- Tool changes need a gateway/omp restart; a running session keeps failing with "rhai is not supported" until then.
- To add another language, extend setup.sh (pin rev, add to customLanguages), not the tracked ~/.config/ast-grep.
- A test config named `sgconfig.yml` placed in an ancestor of the test cwd is treated as a project config by the launcher.
- Never fire several `edit` calls on one file in parallel: they race and drop edits. Line numbers in `PUT` refer to the read snapshot.
- Shell checks here forbid suppression comments (`shellcheck disable`, `foxguard: ignore`); restructure instead (e.g. `"add(\$A)"` instead of single-quoted `$`).
- Mise shim calls to ast-grep can hang under heavy host contention; use `~/.local/share/mise/installs/ast-grep/<ver>/ast-grep` to isolate.
