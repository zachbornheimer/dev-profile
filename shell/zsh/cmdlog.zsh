# Command activity log — for later workflow review (local, plaintext)
# Appends to ~/.cmdlog.tsv:  start-epoch <TAB> duration-ms <TAB> cwd <TAB> command
# Commands that look like they carry a secret are skipped, never logged.
# Pause: comment the two add-zsh-hook lines below.  Clear: rm ~/.cmdlog.tsv
zmodload zsh/datetime 2>/dev/null
typeset -g _CMDLOG_FILE="$HOME/.cmdlog.tsv"
typeset -g _CMDLOG_START="" _CMDLOG_CMD=""
autoload -Uz add-zsh-hook

_cmdlog_preexec() {
	_CMDLOG_START=$EPOCHREALTIME
	_CMDLOG_CMD=$1
}

_cmdlog_precmd() {
	[[ -z $_CMDLOG_CMD ]] && return
	case "$_CMDLOG_CMD" in
	*token* | *secret* | *password* | *passwd* | *apikey* | *api_key* | *doppler* | op\ * | *\ op\ * | *private* | *PRIVATE* | *credential*)
		_CMDLOG_CMD=""
		return
		;;
	esac
	local dur=$(((EPOCHREALTIME - ${_CMDLOG_START:-$EPOCHREALTIME}) * 1000))
	printf '%d\t%.0f\t%s\t%s\n' "${_CMDLOG_START%%.*}" "$dur" "$PWD" "$_CMDLOG_CMD" >>"$_CMDLOG_FILE"
	_CMDLOG_CMD=""
}

add-zsh-hook preexec _cmdlog_preexec
add-zsh-hook precmd _cmdlog_precmd
