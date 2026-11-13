# Dev Profile

The files in this repo are the source. mise dot apply links them into place. There is no Pkl render.

Pins are in languages/<lang>/tools.toml, one file per language, merged by profile/mise.toml through `include`. Hook steps are in hk/hk.pkl. CI installs the pins and runs mise run test.

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
an interactive terminal and never runs for a no-TTY `zsh -lic` command.

## What stays out of this public repo

SSH private keys, home/ssh/config, known_hosts, the opencode password, and agents/hooks/state are gitignored. A clone does not restore them. Automatic pull of tracked files needs a private origin. This repo is not that origin.

## Self-saving dotfiles (`mise dot`) and protections

Tracked live files (`mode = "track"`) stay as regular files in `$HOME` and are checkpointed automatically by the `mise-history` (`history-watch`) LaunchAgent into `~/.local/state/mise/history/repo.git`. Shared profile keys (such as `~/.config/worktrunk/config.toml/dev-profile`) use `merge = true` so `mise dot apply` updates profile-owned keys while preserving hand edits.

Protections enforced on self-saving history:

- **Bare-repo `pre-push` secret scanning**: Git 2.51+ config-based hooks (`[hook "hk-pre-push"]` in `~/.gitconfig`) run on `mise dot origin set`, `mise dot sync`, and `history-watch` pushes even when `mise` sets `core.hooksPath`. `bin/dev-profile-pre-push` preserves `DEV_PROFILE_HOOK_GIT_DIR` across `mise x` and scans bare-repository pushes (`~/.local/state/mise/history/repo.git`) with `gitleaks git`, `betterleaks git`, and private-key header checks without invoking worktree-only `hk` steps.
- **Encryption and exclusions**: `~/.config/mise/age.txt` (`0600`) provides the machine `age` identity for `[history.encryption] recipients`, and `[history] exclude` keeps `age.txt`, `.netrc`, `hooks/state/`, `learnings/`, sockets, logs, and session snapshots out of history.
- **Tripwire**: `agents/hooks/gate-bypass-tripwire.py` blocks `--allow-plaintext-history`, `MISE_HISTORY_ALLOW_PLAINTEXT_HISTORY`, and `allow_plaintext_history = true`.
- **`main` branch isolation**: History sync connects to a dedicated `--branch history` (or dedicated private setup repository), never a repository's protected `main` code branch.

## Checks

Run mise run doctor. Run mise dot apply --dry-run before changing live links.

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

Failed hooks restore tracked content and staged entries, including edits that
preserve file size and timestamps. Snapshot indexes discard Git's stat cache
before hashing files; pre-existing tracked deletions remain deleted.

Run `mise run test:kitty-tabs` with Kitty installed to check custom tab labels, icons, equal widths, and the new-tab button using Kitty's renderer without opening a window. Tab icons in `kitty/tab-icons.conf` accept hexadecimal Unicode codepoints such as `U+E73C` or literal glyphs.
