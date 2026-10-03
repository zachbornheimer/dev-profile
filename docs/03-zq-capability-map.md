# 3. ZQ capability → replacement mapping

Binary: `/Users/zbornheimer/.local/bin/zq` → mise go 1.27.1 install. Version: `zq v0.1.0-746-g5097facb`. Keep installed. Do not add a replacement executable.

`eval "$(zq activate zsh)"` still runs on every interactive shell (`~/.zshrc` 753–755). Phase 1 does not remove it, so zq may still converge hooks beside the new mise profile.

`zq run` already prefers mise tasks when `--platform` is omitted (builtin → mise → makefile → npm → pnpm). That is the migration path.

## Map

| Capability                                            | Class                                | Replacement                                                                                                                               |
| ----------------------------------------------------- | ------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------- |
| `activate` (cd substrate)                             | still-custom                         | Keep in phase 1. Later: mise parent overlay + `mise install` on enter may cover tools; hook install still zq or lefthook                  |
| `adopt`                                               | still-custom / unused-delete         | Org lefthook/pre-commit → zq policy. Revisit after dprint+lefthook profile exists                                                         |
| `all`                                                 | replaced-by-config                   | `mise run ci` once that is the gate                                                                                                       |
| `audit`                                               | replaced-by-tool                     | `mise run scan` (gitleaks/semgrep/govulncheck)                                                                                            |
| `check` / `staged` / pre-commit                       | replaced-by-config                   | lefthook → `mise run fmt` / `mise run check` on staged files. Keep zq hook until that is proven                                           |
| `ci`                                                  | replaced-by-config                   | `mise run ci`                                                                                                                             |
| `clarify`                                             | still-custom                         | Voice/clarity rewrite. Not a Dev Profile job                                                                                              |
| `completion`                                          | replaced-by-tool                     | shell completion; keep while zq stays                                                                                                     |
| `config`                                              | still-custom                         | zq install/prune/hook flags                                                                                                               |
| `coordinate`                                          | still-custom                         | Cross-worktree live-edit collision. Survivor                                                                                              |
| `doctor`                                              | replaced-by-config                   | `mise run doctor` + `mise ls`                                                                                                             |
| `exec`                                                | replaced-by-tool                     | `mise exec` / `mise run`                                                                                                                  |
| `files`                                               | unused-delete                        | Scope listing; `git diff` / `zq` internal                                                                                                 |
| `fix`                                                 | replaced-by-config                   | `mise run fmt`                                                                                                                            |
| `install` / `setup`                                   | replaced-by-config                   | `mise run setup` + mise bootstrap later                                                                                                   |
| `install-hook` / `uninstall-hook`                     | replaced-by-config                   | lefthook via `mise run setup`                                                                                                             |
| `land`                                                | still-custom                         | GitHub check / local verdict reuse (`refs/zq/verdicts/<sha>`). Survivor (expensive-gate coalescing)                                       |
| `port` (claim/env/get/ls/release)                     | still-custom until URL layer         | Later Portless `.localhost` or Worktrunk `hash_port` + Caddy. Do not kill unknown PIDs                                                    |
| `prune`                                               | still-custom                         | Worktree/branch prune + shared node_modules/vendor store. Later Worktrunk `wt step prune` + cowtree compact                               |
| `restore`                                             | still-custom                         | Crash recovery of zq fix stash                                                                                                            |
| `run` / `zqr`                                         | replaced-by-tool                     | `mise run <task>` is the AI contract                                                                                                      |
| `self-update`                                         | unused-delete for profile            | Binary updater                                                                                                                            |
| `session` enter/leave                                 | replaced-by-config                   | Directory-derived mise overlay; `cd` is sufficient                                                                                        |
| `trust`                                               | replaced-by-tool                     | `mise trust`                                                                                                                              |
| `uninstall`                                           | still-custom                         | Reverse zq setup                                                                                                                          |
| `update`                                              | replaced-by-config                   | Org overlay → git:: include / parent mise.toml                                                                                            |
| `version`                                             | keep                                 | Identity of remaining binary                                                                                                              |
| `worktree`                                            | still-custom until Worktrunk default | Canonical path `~/Developer/<Org>/.worktrees/<repo>-<slug>/`. Worktrunk `wt switch` should honor that layout, not replace cowtree compact |
| pre-push / introduced-vs-existing / affected-Go-tests | still-custom                         | Do not recreate the whole gate framework. Extract later only if still used                                                                |

## Phase 1 implication

zq remains the hook/gate while Personal directory selection moves to mise. Success is `cd` + `mise run fmt|test`, not `zq` going away.
