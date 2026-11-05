# hk documentation, digested

Docs version 2.11.1; this machine runs **2.11.0** (mise shim). Every fact below is from
<https://hk.jdx.dev>; the page is named per section. Where the docs are silent, this says so.

## 1. Model

- `why-hk.html`: hk is built for many linters over overlapping files. It runs steps concurrently and
  tracks **read/write file locks** for "the files selected by each step". Literal: _"This relies on
  accurate step definitions. A check must be read-only, and a step must declare the files its commands
  may touch. Commands that modify undeclared files bypass that protection. Use `depends` or `exclusive`
  when a tool's effects extend beyond its selected files."_
- Read-only checks hold read locks; fixers hold write locks on their step's files; unrelated steps run
  in parallel up to the job limit (`HK_JOBS`, default = CPU count).
- `hooks.html`: _"A hook is a named collection of steps."_ `check`/`fix` are hooks too, reachable as
  `hk check` / `hk fix`.

## 2. Configuration

- Files (`configuration.html#config-file-paths`): hk walks upward and takes the **first** match of
  `hk.local.pkl`, `.config/hk.local.pkl`, `hk.pkl`, `.config/hk.pkl` — _"hk selects one project file; it
  does not merge every file it finds."_ `HK_FILE` replaces the search.
- **User config**: `~/.config/hk/config.pkl` (`HK_CONFIG_DIR`, `XDG_CONFIG_HOME`). _"For user files
  amending `Config.pkl`, hooks and steps merge additively with the project: user configuration adds
  names the project does not define, and project definitions win on collisions."_ "Global configuration
  is separate from global hook installation."
- Precedence, lowest→highest (`configuration.html#configuration-precedence`): built-in defaults → user
  config → project config → git config (local over global) → `HK_*` → CLI flags. Scalars: higher layer
  wins. Lists (`exclude`, `skip_steps`, `skip_hooks`, `hide_warnings`): **combine** across sources.
- Git config: `hk.jobs`, `hk.skipSteps`, `hk.skipHook`, `hk.failFast`, `hk.exclude` (repeatable),
  `hk.stashLockTimeout`.
- Pkl (`pkl_introduction.html`): `amends` the schema (`Config.pkl`) for allowed properties, `import` the
  `Builtins.pkl` module; **keep both package URLs on the same version**. `local` for helper values.
  `new Mapping<String, Step> { ["name"] = value }`. Amending: `["x"] = (Builtins.x) { prop = … }` —
  _"Assigning a new list replaces that property's list; it does not automatically append to it."_ Raw
  strings `#"..."#` for quotes/backslashes; `import* "generated/*.pkl"` for glob imports. The evaluated
  config is cached (`HK_CACHE`, `hk cache clear`); env reads are in the cache key, file reads are not.

## 3. File selection

`hooks.html#file-selection`:

| invocation                               | default selection                           |
| ---------------------------------------- | ------------------------------------------- |
| `hk run pre-commit`                      | staged files                                |
| `hk check` / `hk fix`                    | modified: staged, unstaged, untracked       |
| `hk check --all`                         | tracked + eligible untracked                |
| `hk check --staged`                      | staged paths, current working-tree contents |
| `hk check --from-ref main --to-ref HEAD` | paths changed between refs                  |

- Stashing changes the default selection to staged files. `--staged` does **not** stash unstaged edits.
- `cli/run.html`: `--files0-from <PATH>` — _"Read the exact file list from a NUL-delimited file, or from
  stdin with `-` (except hooks that reserve stdin)"_. Other selection flags: `--all`, `--staged`,
  `--unstaged`, `--glob`, `--exclude`, `--from-ref`/`--to-ref`, `--pr`, `--step`, `--skip-step`,
  `--plan`, `--why`, `--stats`, `--format human|json|jsonl`, `--sarif`, `--junit-xml`, `--safe`,
  `--stash`, `--stage`/`--no-stage`, `--fail-fast`/`--no-fail-fast`.
- Per-event commands (`cli/run/*.html`): every event takes the same selection flags plus a positional
  `[FILES]…` (which conflicts with `--all`, `--files0-from`, `--pr`, `--staged`, `--unstaged`). Pre-push
  reads git's ref lines from stdin — `<local ref> <local sha> <remote ref> <remote sha>` — keeps the raw
  text in `hook_stdin`, and derives its range from the **first ref only**: `<remote sha>..<local sha>`,
  falling back to the remote-tracking branch and then the default branch. Malformed lines are dropped
  with a warning; deletions (all-zero remote sha) are kept so the empty-ref guard can short-circuit.
  `--files0-from -` is refused on exactly two events, with `"--files0-from - cannot be used with pre-push
  because the hook reads refs from stdin"` (post-rewrite has the equivalent); a path always works.
  Template variables: `hook_args`, `hook_stdin`, `commit_msg_file`, `prev_head`, `new_head`,
  `is_branch_checkout`, `source`, `sha`.

## 4. Steps

Schema (`configuration.html#hooks-hook-steps-step`) — 44 fields, notably: `glob`, `types`, `match_any`,
`allow_binary`, `allow_symlinks`, `check`, `check_list_files`, `check_diff`, `apply_check_diff`,
`check_after_diff`, `check_failed_files`, `fix`, `check_first`, `batch`, `batch_min_files`, `stomp`,
`workspace_indicator`, `prefix`, `dir`, `profiles`, `profile_condition`, `depends`, `allow_failure`
(boolean or expression, e.g. `env('KNOWN_BROKEN') == 'true'`), `shell`, `stage`, `exclusive`, `exclude`,
`interactive`, `stdin`, `condition`, `step_condition`, `hide`, `output_summary`, `diagnostic_format`,
`diagnostic_tool`, `diagnostic_severity`, `env`, `tests`. **There is no step `timeout`.**
Hook fields: `enabled`, `fix`, `stage` (default true for pre-commit), `stash`, `env`, `fail_on_fix`,
`timeout` (whole hook, `"1m30s"` units), `report` (runs with `HK_REPORT_JSON`), `steps`.

- `{{files}}` = the step's selected files; `{{workspace}}`, `{{workspace_indicator}}`,
  `{{workspace_files}}` for workspace-partitioned steps (`workspace_indicator` = one job per matched
  workspace, `dir = "{{workspace}}"`).
- Commands are **Tera** templates: `{{` starts an expression, so a Go-template argument needs
  `{% raw %}…{% endraw %}`.
- Structured commands (`new Command { argv = List(…) }`) pass argument boundaries literally; a standalone
  `{{files}}` argv entry expands to one argument per file. Cannot combine with `shell`/string `prefix`.
- Optimizations: `check_diff` (patch computed under read locks, applied by hk), `check_list_files`
  (+ `check_failed_files` to focus `check` on failing files), `check_first`, `apply_check_diff = false`,
  `check_after_diff`, `batch`, `diagnostic_format` (gcc, gcc-paren, sarif, eslint-json, cargo-json,
  rustc, rustfmt, stylish, tsc, shellcheck, pyright, biome) — _"A step reports diagnostics only when it
  sets `diagnostic_format`"_, and most builtins do not.
- `exclusive = true` waits for earlier steps and blocks later ones; `depends` orders one step;
  `Group` is a scheduling boundary whose children run together and which inherits `dir`/`prefix`/`shell`/
  `stage`/`exclude`/`workspace_indicator`; `profiles`/`profile_condition` gate optional steps;
  `condition`/`step_condition` are expr-lang with `git.staged_files`, `exec_ok('…')`, `exec('…')`.
- Step-level `tests { … }` blocks exist and run via `hk test [--list] [--name …] [--step …]`.

## 5. Builtins

`builtins.html`: builtins are Pkl step definitions supplying file patterns, check/fix commands and
optimizations. **They do not install tools** — the executable must be on `PATH` (or reached via
`prefix`, e.g. `prefix = List("mise", "x", "--")`, `"aube exec"`). `hk builtins` lists them.
`references/our-config.md` records the ones our config uses, with their exact commands.

## 6. Install, bypass, agents

- `cli/install.html`: `hk install --global` (Git 2.54+) writes config-based hooks (`hook.hk-*`) into the
  **user git config**, so every repository on the machine runs hk; a repository without a project config
  gets a silent no-op. `--legacy` writes `.git/hooks/` shims. `--force-local` installs locally even when
  a global install exists (otherwise skipped to avoid running twice). The global launcher passes
  `--staged --from-hook` and follows the hook's own `stash` setting, ignoring `HK_STASH`.
  `security.html`: the globally installed hook runs _"in every repository on the machine … including a
  repository you have just cloned, before you have read its `hk.pkl`"_; with no project config _"hk exits
  silently. It does not load the user config."_ Opt-outs: `HK=0 git commit`, `git config --local
  hook.hk-pre-commit.enabled false`.
- Bypass/skip: `HK=0` (launcher), `HK_SKIP_HOOK`/`HK_SKIP_HOOKS`, `HK_SKIP_STEPS`, `git config hk.skipHook`
  / `hk.skipSteps`.
- `security.html`: _"hk runs the commands your configuration declares. Treat `hk.pkl` like a Makefile…
  hk has no trust prompt and no sandbox."_ `--safe` refuses a run when any step command's **declared**
  effect is unknown or destructive; only `CommandSpec { command = …; effect = "read"|"write"|"destructive" }`
  declares one — _"A plain string, `Script`, or `Command` has an unknown effect. Most builtins declare
  effects."_ `--safe` does not sandbox, does not check `report`, and does not restrict Pkl evaluation.
- `agents.html`: `hk agent instructions|hooks|mcp --target …` print snippets to stdout (never edit host
  config). Portable agent invocation:
  `{ git diff --name-only -z; git diff --cached --name-only -z; git ls-files --others --exclude-standard -z; } | hk run check --files0-from - --safe --format jsonl`.
  Per-step structured `output` is capped at 64 KiB; a structured stream over 16 MiB fails an MCP run.
  `hk mcp --root <project>` = STDIO server, no network port. MCP `scope`: `all` (= `--all`),
  `changed` (= `--stash none`), `unstaged` (= `--unstaged`), `staged` (= `--staged`).
  `hk agent stop-hook` runs `hk run check --safe` as an agent Stop hook, always exits 0, prints
  `{"decision":"block","reason":"…"}` on block.

## 7. Stashing, signals, recovery

`hooks.html#stashing-and-partial-commits`:

- A hook with `fix` + `stash = "git"` saves unstaged work, runs against staged content, stages
  applicable fixes, and restores. Linters still operate on **whole files**.
- hk keeps its stash entry under **`refs/hk/stash/<commit-id>`**, not on the git stash stack — _"`git
  stash list` does not show these entries"_ in this version. Recover with
  `git stash show -p <commit-id>` / `git stash apply <commit-id>`, then
  `git update-ref -d refs/hk/stash/<commit-id>`.
- Locks: `hk-stash.lock` in the worktree's git dir (a second hk in the same worktree waits
  `HK_STASH_LOCK_TIMEOUT`, default 300s, `0` = fail at once) and `hk-pending-stash.lock` guarding the
  journal `hk-pending-stash`. Linked worktrees do not wait for each other.
- Signal handling: SIGINT/SIGTERM/SIGHUP stop the steps, restore the stash, remove the journal and exit
  `128+signal` (143/129); Ctrl+C exits with the run's status. SIGKILL/crash leaves the journal and the
  stash; the next hk run in that repository recovers it **when the worktree has no unstaged changes and
  no untracked files**, otherwise hk prints the exact `git stash apply <commit-id>` to run. Backup
  patches: `<common-git-dir>/hk/patches/` (or `$HK_STATE_DIR/patches/`), `stash_backup_count` (20).
- `git add -N` files are set aside in their own entry and restored as intent-to-add.

## 8. Environment variables

`environment_variables.html`, complete as of 2.11.1:

- Selection/mode: `HK_FILE`, `HK_EXCLUDE`, `HK_SKIP_HOOK(S)`, `HK_SKIP_STEPS`, `HK_STAGE`, `HK_STASH`,
  `HK_STASH_UNTRACKED`, `HK_STASH_BACKUP_COUNT`, `HK_STASH_LOCK_TIMEOUT`, `HK_WALK_IGNORE`, `HK_CHECK`,
  `HK_FIX`, `HK_CHECK_FIRST`, `HK_PROFILE(S)`.
- Output: `HK_LOG`/`HK_LOG_LEVEL`, `HK_LOG_FILE`, `HK_LOG_FILE_LEVEL`, `HK_OUTPUT_FILE`,
  `HK_SUMMARY_TEXT`, `HK_HIDE_WHEN_DONE`, `HK_HIDE_WARNINGS`, `HK_DISPLAY_SKIP_REASONS`, `HK_JSON`,
  `HK_TERMINAL_PROGRESS`, `HK_TIMING_JSON`, `HK_TRACE`, `HK_WARNINGS`, `HK_REPORT_JSON` (output).
- Execution/state: `HK_JOBS`, `HK_FAIL_FAST` (default **true**), `HK_LIBGIT2`, `HK_CACHE`, `HK_CACHE_DIR`,
  `HK_STATE_DIR`, `HK_MISE`, `HK` (launcher bypass).
- Pkl/network (read before `hk.pkl` evaluates, so not settable inside it): `HK_PKL_CACHE_DIR`
  (`~/.cache/pklr` on Linux), `HK_PKL_EMBEDDED` (the running version's package is embedded and seeded —
  a config pinned to it needs no network), `HK_PKL_OFFLINE`, `HK_PKL_HTTP_REWRITE`,
  `HK_PKL_CA_CERTIFICATES`, `HK_PKL_BACKEND` (only `pklr` accepted), proxy vars.

## 9. CI, debug, migration

- `ci.html`: `hk validate` then `hk check --all`; no `hk install` needed. `mise install` +
  `mise exec -- hk check --all`. Branch-scoped: `hk check --from-ref origin/main --to-ref HEAD` (needs
  both refs and enough history). Diagnostics: `--no-fail-fast`, `--plan --json`, `--format jsonl`,
  `--sarif`, `--junit-xml`, `HK_TIMING_JSON`. _"Step time merges overlapping intervals within that step.
  Different steps can overlap, so their durations do not sum to total run time."_
- `logging.html`: start with `hk check --plan`, `--why <step>`, `-v`/`-vv`, `hk validate -v`,
  `hk config dump|get|explain`, `HK_CACHE=0 HK_LOG=debug hk validate`. Logs: `<git-dir>/hk/hk.log`, failed
  command output `<git-dir>/hk/output.log`. Hook not firing twice: inspect
  `git config --show-origin --get-regexp '^hook\.hk-'` and `core.hooksPath`.
- `migration-v2.html`: v1 inputs removed (`hk.toml`/`yaml`/`json`, project `.hkrc.pkl`, home
  `~/.hkrc.pkl`, `--hkrc`, `UserConfig.pkl`, `defaults { }`, `Types.Regex`, `hk generate`). Top-level
  `steps` is optional and creates implicit `check`/`fix`/`pre-commit`; `pre-commit` fixes **and stages**
  by default, everything else leaves changes unstaged unless `stage = true`/`--stage`; hk v2 always uses
  its built-in `pklr` evaluator.
- `migrate-husky.html` / `migrate-lefthook.html`: manual translation tables (no converter for lefthook);
  `hk migrate pre-commit` converts the pre-commit framework.

## 10. `hk util` commands

21 utils. **Exit `1` means "found a problem", `0` clean** for every check util (from the source; the
pages do not print codes). Exactly five write files: `end-of-file-fixer`, `trailing-whitespace`,
`mixed-line-ending` (all only with `--fix`), `fix-byte-order-marker` (always), `fix-smart-quotes`
(by default; `--check`/`--diff` report only). `format-diff` and `sarif-diff` print a patch and exit `1`
when they produced one. Everything else is read-only.

| util                                                                                                                                                                                                               | usage                                                        | notes                                                                                                                                                                                                                  |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `check-added-large-files`                                                                                                                                                                                          | `[--maxkb <KB>] <FILES>…`                                    | default 500 KB; **no added-only flag** — restricting to added files is hk's file selection, not this util                                                                                                              |
| `check-conventional-commit`                                                                                                                                                                                        | `[--allowed-types …] [--allowed-scopes …] <COMMIT_MSG_FILE>` | types default `build,chore,ci,docs,feat,fix,perf,refactor,revert,style,test`; scopes unset = any scope, empty list = unscoped only; `fixup!`/`squash!`/`amend!`/`Merge …`/`Revert "` titles pass; ignores `#` comments |
| `check-merge-conflict`                                                                                                                                                                                             | `[--assume-in-merge] <FILES>…`                               |                                                                                                                                                                                                                        |
| `no-commit-to-branch`                                                                                                                                                                                              | `[--branch <A,B>]`                                           | default `main,master`; a supplied list replaces it; inspects `git symbolic-ref`; detached HEAD is not an error; takes no file list                                                                                     |
| `detect-private-key`, `check-case-conflict`, `check-symlinks`, `check-executables-have-shebangs`, `check-shebang-scripts-are-executable`, `check-byte-order-marker`, `python-check-ast`, `python-debug-statements` | `<FILES>…`                                                   | file list required                                                                                                                                                                                                     |
| `destroyed-symlinks`, `forbid-submodules`                                                                                                                                                                          | `[PATHS]…`                                                   | **no arguments means the whole repository**                                                                                                                                                                            |
| `end-of-file-fixer`, `trailing-whitespace`, `mixed-line-ending`, `fix-smart-quotes`                                                                                                                                | `[-d --diff] [-f --fix] <FILES>…`                            | `--diff` cannot combine with `--fix`                                                                                                                                                                                   |
| `format-diff`                                                                                                                                                                                                      | `[--no-stdin] <FILES>… -- <COMMAND>…`                        | `{}` is the file path; prints a unified diff; a failing COMMAND's own status wins                                                                                                                                      |
| `sarif-diff`                                                                                                                                                                                                       | `[--findings-exit-code <CODE>] -- <COMMAND>…`                | turns a SARIF log's fixes into a patch                                                                                                                                                                                 |

## 11. Documented gaps (do not guess)

- Whether a **local** installed hook passes `--staged --from-hook` (only the global launcher is documented).
- Whether `hk cache clear` also clears `HK_PKL_CACHE_DIR`.
- No per-step `timeout` anywhere in the schema or docs — only the hook has one.
