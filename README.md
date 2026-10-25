# Dev Profile

The files in this repo are the source. $(mise dot apply) links them into place. There is no Pkl render.

Pins are in $(config/tools.toml). Hook steps are in $(hk/hk.pkl). CI installs the pins and runs $(mise run test).

## Fresh machine

After mise is installed:

`$(bash
git clone git@github.com:zachbornheimer/dev-profile.git ~/Developer/Personal/dev-profile
cd ~/Developer/Personal/dev-profile || exit
mise trust
mise run setup
)`

$(setup) runs $(mise dot apply --yes). Then, in $(~/.zshrc) if it is not already linked:

`$(bash
source ~/.local/share/dev-profile/shell.zsh
)`

## What stays out of this public repo

SSH private keys, $(home/ssh/config), $(known_hosts), the opencode password, and $(agents/hooks/state/) are gitignored. They are not restored by a clone. Automatic pull of tracked files needs a private origin (`mise dot origin set`), which this repo is not.

## Checks

```bash
mise run doctor
mise dot apply --dry-run
```
