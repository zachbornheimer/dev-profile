---
name: hk
description: >-
  Operate hk, the git hook runner behind this machine's commit-msg, pre-commit and pre-push gates
  (jdx/hk, Pkl configuration). Use it whenever work touches hk.pkl — the shared file at
  ~/Developer/Personal/dev-profile/hk/hk.pkl that every repository inherits through
  ~/.config/hk/config.pkl — or bin/dev-profile-pre-push, or the hook fixtures under dev-profile/tests:
  reading or editing a step, converting a hand-written step to an hk builtin, deciding whether a
  wrapper must stay, adding or moving a gate, bounding a hook's runtime, or debugging a hook that is
  slow, wedged, refuses a push it should allow, judges files the push did not introduce, blocks on
  debt the branch inherited, or stages work nobody staged. Also load it when a hook fixture goes red
  after a config change, when hk's stash or locks collide with wt tree-for-changes or git stash, and
  before claiming any hk change works.
---

# hk

hk is a Git hook runner: `hk run <hook>` (aliases `hk check`, `hk fix`) runs a named collection of
**steps** concurrently, coordinating them with file locks derived from the files each step declares.
Configuration is Pkl. Version here: **2.11.0** (mise shim). Docs: <https://hk.jdx.dev> — the full
digest with source URLs is in `references/doc-set.md`.

## The model, in one paragraph

**The runner owns file selection; the step declares the files it touches and the commands to run on
them.** pre-commit selects staged files, `hk check`/`hk fix` select modified files, `hk run pre-push`
selects the files between the refs it is handed on stdin, and `hk run … --files0-from <path>` takes an
exact NUL-delimited list instead. hk derives read/write locks from each step's selection, so checks run
alongside each other and fixers serialize on overlapping files. That only works if the declaration is
honest: a command that writes or scans beyond its step's files bypasses the protection, and hk says so
in `why-hk.html` — "Commands that modify undeclared files bypass that protection. Use `depends` or
`exclusive` when a tool's effects extend beyond its selected files."

Two consequences this profile keeps relearning:

1. A **wrapper that re-derives the file list** (`dev-profile-changed-files <tool> -- {{files}}`) is not
   a file-selection mechanism hk can see through; it is a step whose real scope hk cannot lock.
2. A **builtin** is more than a command line: it brings `check_diff` / `check_list_files` / `check_first`
   / `batch` / `allow_binary` / `allow_symlinks` / `exclusive`, so hk can compute a patch under read
   locks, fix only the files that need it, and batch long file lists. A hand-written `check`/`fix` pair
   gets none of that.

## Our layout

| what                                               | where                                                                                                                                                                         |
| -------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| the shared config (all steps, all hooks)           | `~/Developer/Personal/dev-profile/hk/hk.pkl`                                                                                                                                  |
| how every repo gets it                             | `~/.config/hk/config.pkl` → symlink to that file (hk's _user_ config)                                                                                                         |
| the pre-push wrapper (measures the push, calls hk) | `~/Developer/Personal/dev-profile/bin/dev-profile-pre-push`                                                                                                                   |
| per-step helpers still used by policy steps        | `dev-profile-changed-files`, `-push-base`, `-push-introduced`, `-gosec-packages`, `-golangci-ratchet`, `-foxguard-introduced`, `-stylelint-fix`, `-brakeman`, `-bundle-audit` |
| the tests that pin hook behavior                   | `dev-profile/tests/*-fixture.sh`, `tests/run-fixtures.sh`                                                                                                                     |

Config resolution, lowest precedence first: built-in defaults → **user config** (`~/.config/hk/config.pkl`,
`HK_CONFIG_DIR`/`XDG_CONFIG_HOME` move it) → project config → git config → `HK_*` → CLI flags. A user
config **merges additively**: it adds steps and hooks a project does not define, and the project wins on
a name collision. A project's own `hk.pkl` therefore replaces our version of any step it names. Project
discovery walks upward and takes the first of `hk.local.pkl`, `.config/hk.local.pkl`, `hk.pkl`,
`.config/hk.pkl` — one file, never a merge; `hk.local.pkl` replaces the shared file unless it
`amends` it. `HK_FILE=<path>` pins one file.

### How a hook actually fires here

hk is installed **globally** as Git config-based hooks (`hk install --global`), so no repository needs a
local install and `core.hooksPath` stays empty. The entries, as of 2026-11-05
(`git config --global --get-regexp '^hook\.hk-'`):

```ini
hook.hk-pre-commit.command = test "${HK:-1}" = "0" || … mise x hk -- dev-profile-restore-tree-on-failure hk run pre-commit --staged
hook.hk-pre-push.command    = test "${HK:-1}" = "0" || DEV_PROFILE_HOOK_GIT_DIR="${GIT_DIR:-}" … mise x hk -- dev-profile-pre-push
hook.hk-commit-msg.command  = test "${HK:-1}" = "0" || … mise x hk -- hk run commit-msg
```

So every hook runs through `mise x hk --` (mise-managed hk and tools on `PATH`), `HK=0` short-circuits
all of them, and our wrappers sit in front of hk for pre-commit and pre-push.

Verified the same day: in a repository with **no** project config (`dev-env`), `hk run pre-commit --plan`
plans the shared steps — the user config _is_ loaded. The 2.11.1 docs say the opposite ("with no project
config, hk exits silently. It does not load the user config"), which describes the global launcher in
that release; trust the measurement and re-check after an hk upgrade.

hk discovers only `hk.pkl`, `.config/hk.pkl`, `hk.local.pkl`, `.config/hk.local.pkl`. A config kept at
`hk/hk.pkl` — dev-profile's, and the stale copy in dev-env — is live **only** because
`~/.config/hk/config.pkl` symlinks to it; nothing else reads it.

`hk validate --deny-warnings` exits non-zero on the warnings that matter before merging a config change:
unknown properties (release builds drop them silently), a `depends` that orders nothing, a step with no
command, a glob that cannot match.

## Validating and inspecting without running a hook

```bash
HK_FILE=hk/hk.pkl hk validate              # schema + Pkl evaluation, no steps run
hk config sources                          # what hk resolved, in precedence order
hk config dump | hk config get exclude | hk config explain jobs
hk run pre-push --plan                     # which steps, on which files — no execution
hk run pre-push --why <step>               # why a step was included or skipped
hk run pre-commit --stats                  # file counts per step
HK_TIMING_JSON=/tmp/hk-timing.json hk check --all   # per-step wall time
HK_LOG=debug hk run pre-commit             # debug log; HK_LOG_FILE=<path> for the file
```

`HK_OUTPUT_FILE` (default `<git-dir>/hk/output.log`) holds the full output of a failed command.
`hk cache clear` (or `HK_CACHE=0`) clears the evaluated-configuration cache; a stale cache shows up as
edits that do not take effect.

## Gotchas, in the order they bite

1. **No per-step timeout exists.** The Step schema has 44 fields and none of them is a timeout; only the
   **hook** has `timeout = "90s"`. A tool that wedges therefore wedges the whole gate: the push runner
   SIGKILLs the job, `hk run pre-push` dies with `Killed: 9` / "command was cancelled", and _no verdict
   is ever reported_. Bound the risky step itself (inline `timeout -k 30 <budget>` in its command, as
   the foxguard step does, failing closed) and give long hooks a hook `timeout` as the backstop.
2. **Scope you do not declare is scope hk cannot lock.** `gosec ./...`, `go vet ./...`,
   `golangci-lint run ./...`, `cargo-deny --workspace`, `betterleaks dir`, `brakeman`, `bundle-audit`
   and `foxguard diff` all read more than the files handed to the step. Say so: `exclusive = true` plus
   a comment naming the real scope, so hk serializes them instead of pretending they are file-local.
3. **`(Builtins.x) { prop = … }` replaces a property, it does not merge it.** Overriding `glob` or
   `exclude` means repeating every pattern you want to keep. Inspect the builtin's definition first
   (`references/our-config.md` records ours verbatim).
4. **Step names are the public interface.** `hk.skipSteps`, `git config hk.skipSteps`,
   `HK_SKIP_STEPS`, the fixtures and the wrappers all key off the step name; hk's _property_ name
   differs (`Builtins.ox_lint` for our `oxlint`, `Builtins.markdown_lint`, `Builtins.go_vuln_check`).
   Rename the property, never the step.
5. **`{{` starts a Tera expression.** A tool whose own syntax uses braces fails to render — wrap it:
   `kubeconform -schema-location 'https://…/{% raw %}{{.ResourceKind}}{% endraw %}.json' {{files}}`.
6. **`--files0-from` reads a file, or stdin with `-` — and hooks that reserve stdin cannot use `-`.**
   pre-push reserves stdin for the ref list, so our wrapper must write the list to a file and pass the
   path. The list is NUL-delimited; `tr '\n' '\0'` a newline list into it.
7. **hk's stash is not `git stash`.** Entries live under `refs/hk/stash/<commit-id>` and do **not** show
   in `git stash list` (2.11); a journal `hk-pending-stash` plus `hk-stash.lock` and
   `hk-pending-stash.lock` sit in the worktree's git dir; backup patches are under
   `<common-git-dir>/hk/patches/` (`stash_backup_count`, default 20). Anything that assumes `refs/stash`
   races hk — observed here as a commit that contained two files nobody staged, while
   `wt tree-for-changes` and hk's pre-commit stash were both manipulating the stack. Recover with
   `git stash apply <commit-id>` (the id from hk's message or the journal), then
   `git update-ref -d refs/hk/stash/<commit-id>`. `HK_STASH_LOCK_TIMEOUT` (default 300s) is how long a
   second hk in the same worktree waits; `0` fails at once. SIGINT/SIGTERM/SIGHUP restore and exit
   `128+signal`; SIGKILL leaves the journal and the next hk run recovers it.
8. **A wedged or killed hook leaves a stash behind**, and the next run restores it only when the tree is
   clean; otherwise hk prints the exact `git stash apply` line. Read hk's message before touching the
   working tree.
9. **Our fixtures pin the mechanism, not the outcome.** `tests/pre-push-refs-fixture.sh` greps the
   wrapper's own `candidate file(s)` / `1 of 1 candidate file(s) introduced by this push` lines
   (lines 83 and 97), and `pre-push-upstream-merge.sh` asserts that a named step ran. Converting a step
   to a builtin, or narrowing candidates in the hook, turns them red _by design_. When the mechanism
   changes on purpose, port the assertion to what hk itself prints
   (`<step> – N file(s) – <glob> – <cmd>`) or to the files the step judged — do not delete the test and
   do not weaken it to a substring that passes either way.
10. **Package URLs are pinned and immutable.** `amends` and `import` must name the same hk version; the
    running version's package is embedded, so a config pinned to _another_ version downloads on first
    use. A cached package never changes — publish a new version to change shared configuration. Offline
    or mirrored: `HK_PKL_OFFLINE`, `HK_PKL_CACHE_DIR`, `HK_PKL_HTTP_REWRITE`, `HK_PKL_CA_CERTIFICATES`.
11. **`fix = true` on a hook rewrites the tree mid-run.** A whole-workspace fixer breaks every whole-tree
    step that runs after it — our `golangci-lint run --fix ./...` rewrote every module mid-push and
    `gosec`/`go vet` then judged the files it had broken. Prefer `check`/`check_diff` (hk applies the
    patch under read locks), keep fixers file-scoped, and reserve `fix` for formatters that only touch
    their own files.
12. **Editing the shared config through a merge is easy to get wrong here.** This repo sets
    `merge.conflictStyle = diff3`, so a conflict carries a `||||||| base` section. Stripping only
    `<<<<<<<`, `=======`, `>>>>>>>` leaves base text in the file; `hk validate` catches it, but read the
    markers you actually have (`grep -nE '^(<<<<<<<|=======|\|\|\|\|\|\|\||>>>>>>>)'`) before editing.

## Why our pre-push is shaped the way it is

A push gate must cost what the push _introduces_, not what the repository _contains_. Four separate
costs were paid in the old design, and each has its own fix (all measured, all landed on main):

| cost                            | symptom                                                                     | fix in place                                                                                              |
| ------------------------------- | --------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------- |
| unreadable refs                 | hk selects every tracked file and every tool walks the tree                 | the wrapper refuses the push (`dev-profile-push-base` failure, or refs that do not match the ref pattern) |
| per-step measurement            | the same diff recomputed per step: tens of seconds of git × dozens of steps | measure once in the wrapper, share `DEV_PROFILE_PUSH_INTRODUCED`                                          |
| tools that ignore the file list | `foxguard diff` walks both sides: 30–70 min on 6.7k TypeScript files        | `dev-profile-foxguard-introduced` + a fail-closed budget (`DEV_PROFILE_FOXGUARD_BUDGET`)                  |
| inherited debt                  | a push blocked by findings it did not write                                 | ratchet wrappers: `dev-profile-golangci-ratchet`, `dev-profile-gosec-packages`, `--added` for large files |

Keep that table in mind before "simplifying" a wrapper away: the wrapper is often the only place a
policy ("only what this push introduces", "only findings in the pushed files") can live.

## Escape hatches

`HK=0 git commit` (bypass the installed launcher) · `HK_SKIP_HOOK=pre-push`, `HK_SKIP_HOOKS`,
`HK_SKIP_STEPS=a,b`, `git config --local hk.skipHook pre-push`, `git config --local hk.skipSteps a,b` ·
`HK_CHECK=1` / `HK_FIX=0` to force check mode · `HK_STASH=none`, `--no-stage`, `--staged` ·
`DEV_PROFILE_ALLOW_DEFAULT_BRANCH_PUSH=1` for the profile's own branch guard · `--safe` refuses
commands whose effect is undeclared.

## Files

- `references/doc-set.md` — the digested hk documentation (every page, facts with URLs).
- `references/our-config.md` — our 45 steps: which map to an hk builtin and which keep a wrapper, with
  the builtin's exact commands.
