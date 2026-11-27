# Dev Profile

The files in this repo are the source. mise dot apply links them into place. There is no Pkl render.

Pins are in languages/<lang>/tools.toml, one file per language, merged by profile/mise.toml through `include`. Hook steps are in hk/hk.pkl. CI installs the pins and runs mise run test.

## Supported agent harnesses

Only omp and the Codex desktop app are supported. Claude Code, the Codex CLI, Grok Build, OpenCode, Hermes, Gemini CLI, Copilot CLI, Cursor, pi and every other agent tool have been removed: no hook, skill, config, package pin or script here is maintained for them. A mention of one of them in this repo is a removal note or legacy data (old session transcripts the tools still read), and is never extended. Add support for another harness only on request.

## Adopt it

Clone this repo anywhere. The path does not matter: after the first apply the profile finds itself from where `~/.config/mise/conf.d/dev-profile` links.

```sh
git clone <this repo> ~/src/dev-profile
cd ~/src/dev-profile
mise trust
mise run setup
```

`setup` seeds `~/.config/mise/config.toml` if it is missing, then runs `mise dot apply --yes` with `MISE_DOTFILES_ROOT` set to the clone. That variable is only needed on that first apply, because every source in the deploy map is relative to `dotfiles.root`, and `profile/mise.toml` sets `dotfiles.root` to the clone once the fragment is linked. To apply by hand on a fresh machine: `MISE_DOTFILES_ROOT=<clone> mise dot apply`.

A `mise run` task started from a git worktree of an already set-up machine leaves the live links on the main checkout.

The core deploys nothing under `~/Developer/Personal`. Machines whose repositories live there add the code-root files (`.editorconfig`, `.golangci.yml`, `deny.toml`, `dprint.jsonc`, `mise.toml`) by linking the overlay:

```sh
ln -s "$PWD/config/personal.toml" ~/.config/mise/conf.d/personal.toml
mise dot apply
```

`mise run test:adoption` proves all of this with the real mise in a scratch HOME. The shell file linked at ~/.local/share/dev-profile/shell.zsh is what a new shell should source.

## Make it yours

- **Owners.** `config/owners` lists the GitHub logins whose repositories the profile treats as its own (trusted mise config, its formatters and hooks apply). Set `DEV_PROFILE_OWNERS` to another file to replace the list without editing a script. `mise run test:owners` covers it.
- **Agent stack.** `mise run setup:personal` adds the author's upstream skills and omp setup on top of `setup`. A plain `mise run setup` skips both.

Licensed under the MIT License (see `LICENSE`).

Login zsh loads the `org.zysys.op-service-account` Keychain entry for the current
username in `shell/zsh/05-env.zsh`, before the eager AI environment can call
`op inject`. An inherited service token takes precedence. Unattended shells
disable biometric unlock; desktop token recovery in `06-env.defer.zsh` requires
an interactive terminal and never runs for a no-TTY `zsh -lic` command. That file
asks the 1Password server about a token once per twelve hours (`op vault list`),
not once per shell: the request allowance is shared with every Relay guest. It
keeps the token's SHA-256 under `~/.local/state/dev-profile/`, never the token;
`mise run test:op-token-validation` counts the calls a shell start makes.

`ai-keys::env` runs `op inject` once to fill `~/.cache/ai/keys.env`. When
1Password refuses, a shell that cannot change the answer (no terminal on stdin,
or not macOS: an agent's shell, a Relay guest's) does not ask again for the same
token and template for 15 minutes; a Mac terminal shell and `ai-keys-refresh`
always ask. The record, `~/.cache/ai/keys.env.refused`, holds a SHA-256 of the
token and template, never either one. `mise run test:ai-keys-refusal` counts the
runs.

## What stays out of this public repo

SSH private keys, home/ssh/config and known_hosts are gitignored. A clone does not restore them. Automatic pull of tracked files needs a private origin. This repo is not that origin.

## Self-saving dotfiles (`mise dot`) and protections

Tracked live files (`mode = "track"`) stay as regular files in `$HOME` and are checkpointed automatically by the `mise-history` (`history-watch`) LaunchAgent into `~/.local/state/mise/history/repo.git`. Shared profile keys (such as `~/.config/worktrunk/config.toml/dev-profile`) use `merge = true` so `mise dot apply` updates profile-owned keys while preserving hand edits.

Protections enforced on self-saving history:

- **Bare-repo `pre-push` secret scanning**: Git 2.51+ config-based hooks (`[hook "hk-pre-push"]` in `~/.gitconfig`) run on `mise dot origin set`, `mise dot sync`, and `history-watch` pushes even when `mise` sets `core.hooksPath`. `bin/dev-profile-pre-push` preserves `DEV_PROFILE_HOOK_GIT_DIR` across `mise x` and scans bare-repository pushes (`~/.local/state/mise/history/repo.git`) with `gitleaks git`, `betterleaks git`, and private-key header checks without invoking worktree-only `hk` steps.
- **Encryption and exclusions**: `~/.config/mise/age.txt` (`0600`) provides the machine `age` identity for `[history.encryption] recipients`, and `[history] exclude` keeps `age.txt`, `.netrc`, `hooks/state/`, `learnings/`, sockets, logs, and session snapshots out of history.
- **Tripwire**: `~/.agents/hooks/gate-bypass-tripwire.py` blocks `--allow-plaintext-history`, `MISE_HISTORY_ALLOW_PLAINTEXT_HISTORY`, and `allow_plaintext_history = true`.
- **`main` branch isolation**: History sync connects to a dedicated `--branch history` (or dedicated private setup repository), never a repository's protected `main` code branch.

On macOS, the repair launcher keeps ownership of its worker through the startup
grace period. A worker that exits during that period is reaped and logged as a
startup failure, so the watchdog notifies the user instead of entering cooldown.
Surviving workers keep their own session and outlive the watchdog tick.

## Turn checkpoint provenance

Run `dev-profile-dot-save-turn <ticket> <path>...` to save a turn's snapshot.
The wrapper uses the checkpoint ID from the save receipt, reads the single
checkpoint index and only that record's metadata, and checks schema 2, agent
provenance, task, description, and a complete change set. It never lists history
or reads `latest`, which can belong to another writer. Index parsing is linear
in checkpoint count; metadata reads stay constant. The save itself remains owned
by mise and can still wait for its operation lock.

The report includes modified, added, and removed paths. Named paths appear under
`authored:`; all others appear under `captured-not-authored:`. Quote the latter
verbatim. A missing receipt, unsupported cache format, truncated change set, or
mismatched record fails without printing a capture claim, even if save succeeded.
There is no slow history fallback. `mise run test:dot-save-turn` covers 10,000
unrelated metadata records, concurrent latest checkpoints, rejected provenance,
and real mise saves in an isolated HOME. Doctor runs this same task.

## Shell formatting

dprint owns shell formatting. Bash/POSIX scripts use the existing exec plugin
(0.8.0, needed for shebang filename dispatch) and pinned `shfmt` 3.14.1
(`languages/common/tools.toml`). Zsh keeps the existing sh plugin because shfmt
does not yet parse all of the profile's Zsh syntax. Both the old sh plugin 0.1.2
and its maintained successor `@dprint/shuck` 0.2.7 grow indentation on the
brace-group command substitution in `tests/fixtures/shell-brace-substitution.sh`.
Calling the old plugin's Wasm directly also grows indentation each pass,
independently of dprint's stability check.

The fixture preserves the exact `exclude_copied_output` replacement from
`omp:01a20e37-0793-754f-8a23-188098ea94a6`, with only a Bash shebang and the
existing closing brace appended. Keep these bytes unformatted. Run
`mise run test:dprint-shell` to check convergence, Bash syntax, syntax-tree
preservation (including comments and literals), shell file discovery, and error
propagation. The same regression runs in doctor/CI. Shell extensions, dotfiles
and shebang dispatch remain enabled; dprint's stable-format check stays on.

## Park or retire a clone

`wt done` uses native Worktrunk aliases to commit worktrees, snapshot stashes,
restack checked-out branches, push local tips to origin, and prune integrated
worktrees. It keeps the clone. `wt retire`, `wt drop`, and `wt done --drop` run
the same lifecycle and then move the clone to Trash. `wt done -- --drop` also
works when forwarding the flag explicitly.

Commit and push hooks, scanners, and configured signing remain active. A failed
hook or push stops cleanup. Diverged branches go to `backup/conflicts/<clone>/`
without force-pushing; prior backup tips are never overwritten. Stashes become
signed worktree commits on their original base, including untracked files.
Ignored files are not pushed and remain in the retained clone or Trash.
Linked worktrees with ignored files are retained, including files written by removal
hooks. Removal preserves the original user/project hooks and appends a final
preservation check; a hook that changes work or moves HEAD prevents removal.
Native Worktrunk's prune plan selects integrated worktrees and branches; every
worktree removal is rechecked against that plan after its hooks.
The lifecycle uses the profile's existing Bun and jq tools for native configuration
and prune-plan composition.
The existing `wt` shim carries explicit global `--config` and `-y`/`--yes`
through nested native invocations; it does not grant approval unless requested.

`wt done -- --dry-run` shows status without fetching, committing, pushing or deleting.
`--no-pr`,
`--no-prune`, `--no-commit`, and `--no-push` retain their explicit controls;
retirement refuses unpublished work or remaining linked worktrees. Nested
repositories and files above `DEV_PROFILE_SYNC_MAX_FILE_MB` (default 50 MiB)
stop preservation. Finish ongoing merges or rebases before running `wt done`.
A checkout with every tracked path missing and no staged changes is restored
from HEAD before parking, matching the existing lost-checkout safeguard.
Staged repository-wide deletions and partial deletions remain intentional.

`mise run test:done-native` deploys the **complete** source configuration with
the real mise merge entry over a stale legacy installation, then exercises the
native Worktrunk CLI against local bare remotes. This deployment proof requires
the profile's mise build with `dot apply`; the portable `mise run test:done`
consumer safety suite uses the same complete config directly and remains in
`doctor` for upstream-mise CI. Only forge, Trash, commit-message generation and
workstation-specific hook adapters are sandboxed; Git hooks and signing remain
active. No fixture reconstructs a test-only alias subset.

## Native worktree aliases

`wt sync` rebases the current branch with `wt step rebase` onto
`origin/<default-branch>`, or its explicit `branch.<name>.gh-merge-base` parent.
It does not infer stacks or ask an agent to repair conflicts. A failed rebase or
push propagates failure and leaves the worktree available for resolution.

- `-u`, `-f`, `--fetch`: fetch origin before rebasing.
- `-p`, `--push`: publish to the existing upstream after rebasing, using an exact
  lease on its observed remote-tracking tip. Branches without upstreams are
  reported and skipped; first publication stays explicit (`git push -u`).
- `--push-only`: publish without fetching or rebasing.
- `--branch=NAME`: select a worktree; `--all` visits all checked-out worktrees
  through native `wt step for-each`, not dependency-ordered stack inference.
- `-P`, `--prune`: run native integrated-worktree pruning after successful sync.
- `-n`, `--dry-run`: report options without fetching, rebasing, pushing or pruning.
- `--stack`, `--force`, and unknown options are rejected before mutation. Select
  a branch explicitly or preserve dirty work with `wt done` instead.

`wt prune` delegates to native `wt step prune`. Preservation and retirement use
only the `done` lifecycle; the old `dev-profile-sync`, `dev-profile-prune`, and
`dev-profile-retire` implementations and their bypassing fixtures are removed.
`wt-sync` is no longer called, even if an old installation remains on PATH.

`wt pr`, `wt pr-draft`, and `wt pr-auto` share one native worktree-selection
alias. The latter two select the publication mode and forward to `wt pr`;
`--create=NAME` and an optional post-create command retain their existing forms.
The `dev-profile-pr`/`dev-profile-pr-watch` adapters remain because they own forge
publication and CI watching, not worktree lifecycle. Existing commit-fix,
benchmark, worktree-copy, application-reap and legacy-hook-cleanup adapters keep
their unrelated responsibilities. The `bin/wt` shim still only forwards native
commands, commit-fix, benchmarking, explicit config and approval inheritance.

`mise run test:native-aliases` exercises native sync against real signed scratch
repositories, including dry-run, upstream leases, failed push hooks, selected
worktrees, all-worktree scope and unsupported options.

## Timing a slow `wt land`

Set `WT_BENCH=1` to time every `wt` call and the `gh`, commit and push calls inside `wt land` and `wt pr-auto`; `WT_BENCH=2` also writes worktrunk's own span trace. Run `dev-profile-bench report` for the timeline and slowest calls, or `dev-profile-bench runs` for recent runs. Records go to `~/.local/state/dev-profile/wt-bench.tsv` (override with `WT_BENCH_LOG`). Unset, the `wt` shim runs the real binary untouched.

## Checks

Run mise run doctor. Run mise dot apply --dry-run before changing live links.
Hook fixtures use Git from mise when configured, otherwise the installed Git
on PATH (Homebrew on macOS).

Interactive prompts paint a cached or pure-zsh header before starting Starship,
mise and direnv refreshes, or detached command-log writes. Slow background work
can delay status and environment updates, but never blocks the initial prompt.
The scheduler retains its notification fd between prompts to avoid synchronous
process-substitution cleanup. Directory convergence checks PATH and project
markers only inside its detached worker (`&!`), never in `chpwd`.
`mise run test:cd-latency` exercises held renderers, environment refreshes, and
blocked worker discovery in an interactive terminal.

Fuzzy `cd` and `z` resolve their target with the native zoxide binary selected
by `_zsh_binpath`, without changing PATH or running the mise shim. This lookup
must complete before changing PWD, and it excludes the current directory from
`$PWD` (`${PWD:A}` when the cached init resolves symlinks) with no `pwd`
subshell; `zoxide add` remains detached (`&!`).
The cd fixture uses an isolated database, a failing shim, and a held
`__zoxide_pwd` FIFO to guard this path, plus logical and physical symlink
exclusion.
Linux installs zoxide from the shared mise pin, including on Relay and CI;
macOS uses Homebrew. The fixture checks the native binary before opening its PTY
and uses the real resolver with a scratch direnv executable, without a resolver stub.

The mise config-stamp ancestry walk stops at the filesystem root or an unchanged
parent, so shells started in deleted directories finish startup.

Interactive prompts paint a cached or pure-zsh header before starting Starship,
mise and direnv refreshes, or detached command-log writes. Slow background work
can delay status and environment updates, but never blocks the initial prompt.
The scheduler retains its notification fd between prompts to avoid synchronous
process-substitution cleanup. Directory convergence checks PATH and project
markers only inside its detached worker (`&!`), never in `chpwd`.
`mise run test:cd-latency` exercises held renderers, environment refreshes, and
blocked worker discovery in an interactive terminal.

`mise run test:omp` checks the installed `~/.omp/agent/tools` import graphs and
callable default exports, then loads installed extensions through OMP's real RPC
startup and registration path. It sends no model prompt and executes no tool.
Missing dependencies (including native addons), syntax errors, registration
failures, and startup timeouts fail the command. It does not execute custom-tool
factories or test external services. `OMP_AGENT_DIR=/path/to/agent` selects another
installation. An installation with no entry modules reports `SKIP`, not verified
health. `mise run test` includes this check and isolated regression fixtures;
`mise run test:omp-fixture` runs those fixtures directly.

`mise run test:pre-push-upstream-merge` checks both Git pushes and direct
`hk run pre-push --from-ref <base> --to-ref HEAD` runs. Both judge files authored
by the branch, not unchanged files inherited from published merge parents;
authored lint findings still fail, and the history secret scan stays range-wide.
Direct attribution measures the current checkout at `HEAD`; use `--to-ref HEAD`
for this mode. The hook's tools lint checkout files, not another ref's tree.

`mise run test:foxguard-introduced` runs real foxguard through
`bin/dev-profile-foxguard-introduced`. A target file foxguard cannot parse
contributes no findings, while findings from the target's other files stay
suppressed. A branch file foxguard cannot parse, a scanner failure, or an invalid
comparison fails closed with exit 2.

Failed hooks restore tracked content and staged entries, including edits that
preserve file size and timestamps. Snapshot indexes discard Git's stat cache
before hashing files; pre-existing tracked deletions remain deleted.

Run `mise run test:kitty-tabs` with Kitty installed to check custom tab labels, icons, equal widths, and the new-tab button using Kitty's renderer without opening a window. Tab icons in `kitty/tab-icons.conf` accept hexadecimal Unicode codepoints such as `U+E73C` or literal glyphs.
