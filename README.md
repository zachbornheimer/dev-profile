# Dev Profile

The files in this repo are the source. mise dot apply links them into place. There is no Pkl render.

Pins are in config/tools.toml. Hook steps are in hk/hk.pkl. CI installs the pins and runs mise run test.

## Fresh machine

After mise is installed, clone this repo to ~/Developer/Personal/dev-profile, then run mise trust and mise run setup in that directory.

setup runs mise dot apply --yes. The shell file linked at ~/.local/share/dev-profile/shell.zsh is what a new shell should source.

## What stays out of this public repo

SSH private keys, home/ssh/config, known_hosts, the opencode password, and agents/hooks/state are gitignored. A clone does not restore them. Automatic pull of tracked files needs a private origin. This repo is not that origin.

## Checks

Run mise run doctor. Run mise dot apply --dry-run before changing live links.
