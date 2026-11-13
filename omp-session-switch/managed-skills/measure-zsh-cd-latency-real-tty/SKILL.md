---
name: measure-zsh-cd-latency-real-tty
description: "Use when you must measure how long a zsh cd takes (Enter to prompt) on this Mac and which chpwd/precmd/preexec hook costs it; real-tty harness with script(1), plus pitfalls that wasted hours."
---

# Measure zsh cd latency on a real tty

Non-tty `zsh -ic` takes a different, synchronous prompt path and misleads. Time on a tty.

## Harness (works)
- Pipe typed lines into `script -q /dev/null zsh -i >raw 2>&1`. Lines: `cd /tmp`, `print -r -- "LAT_${_cdlat_last_ms}_END"`, `cd <target>`, same print, `exit`; end the producer with `zselect -t 4000` (zsh/zselect) so stdin stays open until zsh has processed everything.
- Read results with `grep -ao 'LAT_[0-9.]*_END'`. `_cdlat_last_ms` comes from `~/.config/zsh/cd-latency.zsh` (preexec to zle-line-init, lone cd verbs only).
- First sample is a warm-up (deferred modules load); drop it. Expect big run-to-run variance; take medians of 6+.
- `zsh/zpty` harnesses hung silently here (`zpty -r` blocks waiting for a newline). Do not use.

## Per-hook breakdown
Wrap each function in `$preexec_functions $chpwd_functions $precmd_functions` with an `eval`-defined wrapper that appends `cmd<TAB>name<ms>` to a log (use `print -r` and a real tab). Guard against wrapping twice (`_dev_profile_mise_refresh` is in both chpwd and precmd lists; double wrap recurses and hangs). Aggregate per hook with medians, only rows where the running command was `cd ...`.
Hooks inside a background render (`exec {fd}< <(_p_render_full)`) show up in the log but do not block the cd.

## Known costs on this machine
- The mise shim (`~/.local/share/mise/shims/<tool>`) costs 0.5-0.9 s per call; real binary in /opt/homebrew/bin is about 10 ms. Anything on the cd path must be pure zsh or detached with `&!`.
- `defaults read`, autosuggestion rebind per precmd (set `ZSH_AUTOSUGGEST_MANUAL_REBIND=1`), `git` forks in chpwd hooks.
- When the box is loaded (several omp processes at 50-80% CPU) even `cat` can take 20 s: timings are then invalid; re-run when idle.

## Tool pitfalls hit in this workflow
- `run_command` runs bash: zsh-only syntax (`${f:t}`) silently misbehaves; use `basename`. `sleep` and `find` and `grep -r` are refused.
- Commit hooks and `wt merge` each take minutes: run in background with a long timeout and `wait`. `wt merge` removes the worktree and branch, so make a new `wt switch -c <branch> --no-cd` for each follow-up change.
- `~/.local/share/dev-profile/bin` is a symlink to the main checkout's `bin/`; new scripts only go live after `wt merge -y main`.
- A write/edit under the main checkout auto-forks into some existing worktree: check where the file actually landed.
- The commit formatter rewrites `shell/zsh/*.zsh` whitespace; copy the committed file back to `~/.config/zsh/` so live == repo.
- Back up a live file to `~/.local/state/dev-profile/backups/` before overwriting; the repo copy of some modules lags live.

## Trigger for slow cds
`dev-profile-cd-latency <ms> <dir> <log>` starts one detached `omp -p` fixer, with lock + 30 min cooldown; test it with a fake `omp` on PATH, never the real one.
