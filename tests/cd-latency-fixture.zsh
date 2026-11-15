#!/bin/zsh -f
# A held renderer must not delay either the current-directory or cd prompt.
setopt err_exit no_unset
zmodload zsh/zpty zsh/zselect zsh/datetime
root=${0:A:h:h}
[[ -n ${CD_TEST_ROOT:-} ]] && root=$CD_TEST_ROOT
work=$(mktemp -d)
trap 'zpty -d prompttest 2>/dev/null || true; rm -rf "$work"' EXIT
mkfifo "$work/render"
export CD_TEST_ROOT=$root CD_TEST_WORK=$work
zpty -b prompttest zsh -dfi
typeset buffer=''
expect() {
	local needle=$1 chunk=''
	local -F until=$((EPOCHREALTIME + ${2:-3}))
	while ((EPOCHREALTIME < until)); do
		if [[ $buffer == *$needle* ]]; then
			buffer=${buffer#*$needle}
			return 0
		fi
		if zpty -r prompttest chunk; then
			buffer+=$chunk
		else
			zselect -t 1 || true
		fi
	done
	print -u2 -- "FAIL: prompt blocked waiting for renderer ($needle)"
	print -u2 -r -- "PTY output: ${(q)buffer}"
	return 1
}
zpty -w prompttest 'ZSH_THEME_MODE=light; builtin source "$CD_TEST_ROOT/shell/zsh/30-prompt.zsh"; _p_render_full() { read -r < "$CD_TEST_WORK/render"; print -r -- RENDERED; }; _p_render_fast() { read -r < "$CD_TEST_WORK/render"; }; _p_starship_bin=fixture; _p_starship_prompt="\${_p_prompt_text}READY> "; PROMPT=$_p_starship_prompt; _p_prompt_dir=; print -r -- BOOTED'
expect $'\r\nBOOTED\r\n' 10
expect 'READY> '
zpty -w prompttest 'print -r -- SECOND'
expect $'\r\nSECOND\r\n'
expect 'READY> ' 1
zpty -w prompttest 'cd /'
expect 'READY> ' 1
# Release a real background render and observe its repaint, not just a prompt.
exec {render_fd}<>"$work/render"
# Superseded renders may still be draining their canceled pipes.
repeat 4 print -u $render_fd -r -- RENDERED
expect 'RENDEREDREADY> '
exec {render_fd}>&-

# A blocked log destination must not block the next command. Queue two records
# before the one deferred callback runs, then verify both snapshots survive.
mkfifo "$work/log"
zpty -w prompttest 'builtin source "$CD_TEST_ROOT/shell/zsh/cmdlog.zsh"; add-zsh-hook -D preexec _cmdlog_preexec; add-zsh-hook -D precmd _cmdlog_precmd; _CMDLOG_FILE="$CD_TEST_WORK/log"; _cmdlog_preexec "echo first"; _cmdlog_precmd; _cmdlog_preexec "echo second"; _cmdlog_precmd; _cmdlog_preexec "token=hidden"; _cmdlog_precmd; print -r -- LOGQUEUED'
expect $'\r\nLOGQUEUED\r\n'
expect 'READY> '
zpty -w prompttest 'print -r -- LOGRESPONSIVE'
expect $'\r\nLOGRESPONSIVE\r\n'
expect 'READY> ' 1
exec {log_fd}<>"$work/log"
IFS= read -r -t 3 -u $log_fd first
IFS= read -r -t 3 -u $log_fd second
[[ $first == *$'\t/\techo first' && $second == *$'\t/\techo second' ]]
# FIFO ordering puts this sentinel after every record from the detached batch.
print -u $log_fd -r -- END
IFS= read -r -t 3 -u $log_fd last
[[ $last == END ]]
exec {log_fd}>&-

# Hold the actual mise refresh's filesystem-check boundary. The prompt must
# appear before that work starts, and its environment must still land later.
mkfifo "$work/mise"
zpty -w prompttest 'mise() { [[ $1 == activate ]] && print -r -- :; }; builtin source "$CD_TEST_ROOT/shell/mise.zsh"; _dev_profile_mise_config_stamp() { read -r < "$CD_TEST_WORK/mise"; _DEV_PROFILE_MISE_NEW=1; }; _dev_profile_mise_run() { print -r -- "export CD_FIXTURE_ENV=ready"; }; _DEV_PROFILE_MISE_STAMP=0; _p_starship_bin=; _p_starship_prompt="\${CD_FIXTURE_ENV:-waiting}READY> "; print -r -- ENVQUEUED'
expect $'\r\nENVQUEUED\r\n'
expect 'waitingREADY> ' 1
exec {mise_fd}<>"$work/mise"
print -u $mise_fd -r -- release
expect 'readyREADY> '
exec {mise_fd}>&-

# Use the installed binary resolver boundary, never the user's .envrc or shims.
mkfifo "$work/direnv"
mkdir -p "$work/home/.local/bin"
printf '#!/bin/sh\nexit 0\n' >"$work/home/.local/bin/direnv"
chmod +x "$work/home/.local/bin/direnv"
zpty -w prompttest 'HOME="$CD_TEST_WORK/home"; add-zsh-hook -D precmd _dev_profile_mise_refresh; add-zsh-hook -D chpwd _dev_profile_mise_refresh; _zsh_binpath() { print -r -- /fixture/direnv; }; builtin source "$CD_TEST_ROOT/shell/zsh/40-direnv.defer.zsh"; _dev_profile_direnv_run() { read -r < "$CD_TEST_WORK/direnv"; print -r -- "export CD_FIXTURE_DIRENV=applied"; }; _p_starship_prompt="\${CD_FIXTURE_DIRENV:-pending}READY> "; _dev_profile_direnv_hook; print -r -- DIRENVQUEUED'
expect $'\r\nDIRENVQUEUED\r\n'
expect 'pendingREADY> ' 1
exec {direnv_fd}<>"$work/direnv"
print -u $direnv_fd -r -- release
expect 'appliedREADY> '
exec {direnv_fd}>&-
# A worker availability check can scan PATH after mise changes it. It must
# run in the detached worker, not chpwd or the ZLE callback.
mkfifo "$work/enter"
zpty -w prompttest 'builtin source "$CD_TEST_ROOT/shell/zsh/50-enter-converge.defer.zsh"; _enter_converge_enabled() { read -r < "$CD_TEST_WORK/enter"; return 1; }; _enter_converge_chpwd; print -r -- ENTERQUEUED'
expect $'\r\nENTERQUEUED\r\n'
expect 'appliedREADY> ' 1
zpty -w prompttest 'print -r -- ENTERRESPONSIVE'
expect $'\r\nENTERRESPONSIVE\r\n'
expect 'appliedREADY> ' 1
exec {enter_fd}<>"$work/enter"
print -u $enter_fd -r -- release
exec {enter_fd}>&-
print -r -- 'cd-latency fixture ok'
