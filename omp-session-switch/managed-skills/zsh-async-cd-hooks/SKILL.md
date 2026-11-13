---
name: zsh-async-cd-hooks
description: "Use when zsh cd or prompt is slow because chpwd/precmd hooks (mise hook-env, direnv export) fork synchronously, or a stray \"Password:\" appears after cd from the dev-profile-enter worker."
---

Layout (this machine): live shell modules are ~/.config/zsh (tracked by `mise dot`, synced into repo shell/zsh by the watcher); mise init is repo shell/mise.zsh, symlinked to ~/.local/share/dev-profile/mise.zsh and sourced by 05-mise.zsh. shell/shell.zsh just sources mise.zsh + `wt config shell init zsh`.

Pattern for async hooks: `_dev_profile_async_eval NAME FN` (in shell/mise.zsh) runs FN (prints shell code) via `exec {fd}< <($fn)` and registers `zle -F $fd handler`; the handler reads to EOF, evals, queues one re-run if requested meanwhile, then `zle reset-prompt`. `_dev_profile_async_wait` drains synchronously for tests (zle -F handlers only fire at the prompt, so non-interactive `-c` tests must call it). mise: replace `_mise_hook_chpwd`/`_mise_hook_precmd` with `_dev_profile_mise_refresh` calling `<real mise bin> hook-env --shell-pid $$ -s zsh --reason chpwd|precmd`. direnv: drop `direnv hook zsh`, run `direnv export zsh` through the same helper (precmd only when DIRENV_DIR set or an .envrc exists above PWD).

Verify: `bash tests/shell-init-fixture.sh "$PWD/shell"` (absolute path; it cd's elsewhere). Real ZLE check: zsh/zpty driving `zsh -f -i`, cd into a dir with mise.toml, wait, then print the var. Do not use `zsh -i -c` in run_command (host routes it to herdr and fails); write output to a file.

Stuck "Password:" after cd: bin/dev-profile-enter (cd worker) ran `portless proxy start` -> sudo reads the tty. Fix landed 584db32: skip when `dev-profile-dev status` says unconfigured, else `sudo -A -v` with an osascript askpass dialog, decline stamp ~/.cache/dev-profile/enter/proxy-declined (1h).

Pitfalls: the edit tool drops the exec bit on bin/* and tests/*.sh (chmod +x, amend/follow-up commit; check `git commit` output for "mode change 100755 => 100644"). Hashline PUT line numbers: re-read after each edit. Worktree creation (`wt switch -c`) copies ~1.3GiB and can take minutes; run wt/commit/merge in a background run_command and wait.
