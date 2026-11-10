# cd-latency.zsh — time every cd from Enter to the prompt being ready.
#
# Budget: the blocking part of a cd (chpwd hooks, precmd hooks, the prompt
# render the prompt module waits on) stays near 100ms; slower work belongs in
# the background. This measures it on every cd, appends a line to the log when
# it passes CD_LATENCY_SLOW_MS (default 300), and hands that line to
# dev-profile-cd-latency, which starts one detached omp session to fix it.
#
# Start: preexec (Enter). End: zle-line-init, which _p_line_init (30-prompt.zsh)
# calls first thing, after precmd and prompt setup. Async work that lands after
# the prompt (the starship render, background workers) is not part of the cd.
# Only a lone cd verb counts: `cd x && make` is the command's time, not the cd's.
#
# Off: CD_LATENCY_DISABLE=1. Log: CD_LATENCY_LOG (default
# ~/.local/state/dev-profile/cd-latency.log), tab-separated:
#   time  ms  from  to  command

[[ ${CD_LATENCY_DISABLE:-0} == 1 ]] && return 0

zmodload zsh/datetime
autoload -Uz add-zsh-hook

typeset -gF 6 _cdlat_t0=0
typeset -g _cdlat_from="" _cdlat_cmd=""
typeset -gF 1 _cdlat_last_ms=0
typeset -gi _cdlat_slow_ms=${CD_LATENCY_SLOW_MS:-300}
typeset -g _cdlat_log=${CD_LATENCY_LOG:-${XDG_STATE_HOME:-$HOME/.local/state}/dev-profile/cd-latency.log}

_cdlat_is_cd() {
	[[ $1 == *[\;\&\|\`\<\>]* || $1 == *'$('* ]] && return 1
	case ${${(z)1}[1]} in
	cd | z | zi | pushd | popd) return 0 ;;
	esac
	return 1
}

_cdlat_preexec() {
	_cdlat_t0=$EPOCHREALTIME
	_cdlat_from=$PWD
	_cdlat_cmd=$1
}

# Called from zle-line-init. Cheap on every non-cd line: one compare.
_cdlat_line_init() {
	((_cdlat_t0)) || return 0
	local -F 1 ms=$(((EPOCHREALTIME - _cdlat_t0) * 1000))
	local from=$_cdlat_from cmd=$_cdlat_cmd
	_cdlat_t0=0
	[[ $PWD != "$from" ]] && _cdlat_is_cd "$cmd" || return 0
	_cdlat_last_ms=$ms
	((ms > _cdlat_slow_ms)) || return 0
	_cdlat_report "$ms" "$from" "$PWD" "$cmd"
}

_cdlat_report() {
	local stamp
	strftime -s stamp '%Y-%m-%dT%H:%M:%S%z' $EPOCHSECONDS
	[[ -d ${_cdlat_log:h} ]] || command mkdir -p "${_cdlat_log:h}" 2>/dev/null
	printf '%s\t%.0f\t%s\t%s\t%s\n' "$stamp" "$1" "$2" "$3" "$4" >>"$_cdlat_log" 2>/dev/null
	((${+commands[dev-profile-cd-latency]})) || return 0
	dev-profile-cd-latency "$1" "$3" "$_cdlat_log" >/dev/null 2>&1 </dev/null &!
}

add-zsh-hook -D preexec _cdlat_preexec 2>/dev/null
add-zsh-hook preexec _cdlat_preexec
