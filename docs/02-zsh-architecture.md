# 2. Live Zsh architecture audit

Phase 1 does not rewrite the shell. This is the map so later cleanup is local.

## Sourced tree

| File                             | Role                                                        |
| -------------------------------- | ----------------------------------------------------------- |
| `~/.zshenv`                      | Every zsh. uv/pip policy, MAILCHECK=0, Colima/Docker socket |
| `~/.zprofile`                    | Login: re-assert `~/.local/bin` after path_helper           |
| `~/.zshrc`                       | Interactive body (~26k, 11 numbered sections)               |
| `~/.config/zsh/startup-fast.zsh` | Cached inits (`_zsh_eval_cached`), no `mise activate`       |
| `~/.config/zsh/prompt.zsh`       | Async git prompt                                            |
| `~/.config/zsh/nvim-perf.zsh`    | nvim timing                                                 |
| `~/.config/zsh/ssh.zsh`          | kitten ssh + ssh-nas                                        |
| `~/.zshrc.local`                 | q/qf/qa, extra aliases, second zoxide init, `kp`            |
| `~/.zlogin`                      | Present, tiny                                               |

Do not invent `~/.config/zsh/{env,tools,aliases,functions,completion,interactive}.zsh`. That tree already has four real modules.

## PATH construction (order)

1. `~/.zshrc` §1: `~/.local/bin`, mise shims, cargo, `~/go/bin`, composer vendor, Homebrew, then existing `$path`
2. Same file immediately re-prepends `~/.local/bin` and mise shims
3. Perl local::lib prepends `~/perl5/bin` when Homebrew perl exists
4. pnpm block appends `$PNPM_HOME/bin`
5. End of `~/.zshrc` prepends `~/.local/bin` again
6. `~/.zshrc.local` also prepends `$PNPM_HOME/bin`

`typeset -U path` dedupes. Still three explicit PATH writes in one file.

## Activation

- **mise:** shims on PATH. Comment in `~/.zshrc` line 22–24: no `mise activate`, no per-prompt hook-env.
- **uv:** owns Python. Interactive `python`/`python3`/`pip` are functions that refuse system/Homebrew interpreters (`~/.zshrc` 145–206).
- **zoxide:** `~/.zshrc` caches `zoxide init zsh`. `~/.zshrc.local` line 34 also runs `eval "$(zoxide init zsh --cmd cd)"`, which replaces `cd`. Duplicate init; `--cmd cd` is the one that changes `cd`.
- **zq:** `~/.zshrc` 753–755: `_zsh_eval_cached zq -- zq activate zsh && { _zq_reconcile_hook } &!`. `startup-fast.zsh` strips `_zq_reconcile_hook` from the cached file so only the background call remains. Phase 1 keeps this.

## Duplicates and shadows

| Finding                                                   | Where                                                                          |
| --------------------------------------------------------- | ------------------------------------------------------------------------------ |
| `ll` defined twice                                        | `~/.zshrc` eza alias; `~/.zshrc.local` eza alias                               |
| `dns`, `copy-ssh`                                         | both files                                                                     |
| `clean-pyc` / `clean_pyc` / `clear-pyc` / `clear_pyc`     | four aliases, same body, `.zshrc.local`                                        |
| `q` `qf` `qa` `qd` `qr`                                   | `.zshrc.local` → zq. Keep while zq stays                                       |
| `qs`                                                      | `.zshrc.local`; body uses escaped `\$files` so it is currently broken          |
| `ls` `cat` `du` `df` `htop` `grep` `vi` `vim` `view` `gh` | interactive shadows; scripts keep POSIX names if they do not source aliases    |
| `npm` `pnpm` functions                                    | Dropbox xattr after install                                                    |
| `kp <port>`                                               | `kill -9` whatever is on that port — agents must never use this for collisions |

## Env managers

mise shims + uv + direnv hook + zq activate + (optional) perlbrew function. No asdf/nvm/pyenv on the interactive PATH.

## Startup cost

`startup-fast.zsh` exists specifically to avoid `brew shellenv` and `mise activate`. Completions rebuild at most daily (`compinit -C`). Phase 1 leaves this. Timing capture is skipped until a Zsh edit happens (`zsh-startup-unchanged.txt`).
