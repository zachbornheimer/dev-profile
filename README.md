# Dev Profile

The files in this repo are the source. mise dot apply links them into place. There is no Pkl render.

Pins are in languages/<lang>/tools.toml, one file per language, merged by profile/mise.toml through `include`. Hook steps are in hk/hk.pkl. CI installs the pins and runs mise run test.

## Fresh machine

After mise is installed, clone this repo to ~/Developer/Personal/dev-profile, then run mise trust and mise run setup in that directory.

setup runs mise dot apply --yes. The shell file linked at ~/.local/share/dev-profile/shell.zsh is what a new shell should source.

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

Run `mise run test:kitty-tabs` with Kitty installed to check custom tab labels, icons, equal widths, and the new-tab button using Kitty's renderer without opening a window. Tab icons in `kitty/tab-icons.conf` accept hexadecimal Unicode codepoints such as `U+E73C` or literal glyphs.
