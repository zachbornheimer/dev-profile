# Command activity log — for later workflow review (local, plaintext)
# Appends to ~/.cmdlog.tsv:  start-epoch <TAB> duration-ms <TAB> cwd <TAB> command
# Commands that look like they carry a secret are skipped, never logged.
# Pause: comment the two add-zsh-hook lines below.  Clear: rm ~/.cmdlog.tsv
zmodload zsh/datetime 2>/dev/null
typeset -g _CMDLOG_FILE="$HOME/.cmdlog.tsv"
typeset -g _CMDLOG_START="" _CMDLOG_CMD=""
typeset -ga _CMDLOG_PENDING=()
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
	local record
	printf -v record '%d\t%.0f\t%s\t%s' "${_CMDLOG_START%%.*}" "$dur" "$PWD" "$_CMDLOG_CMD"
	_CMDLOG_CMD=""
	_CMDLOG_PENDING+=("$record")
	if [[ -o zle && -t 0 ]] && ((${+functions[_p_after_prompt_defer]})); then
		_p_after_prompt_defer _cmdlog_append
	else
		_cmdlog_append
	fi
}

_cmdlog_append() {
	((${#_CMDLOG_PENDING})) || return 0
	local -a records=("${_CMDLOG_PENDING[@]}")
	_CMDLOG_PENDING=()
	# Snapshot before detaching: a later command must not overwrite this batch.
	(printf '%s\n' "${records[@]}" >>"$_CMDLOG_FILE") &!
}

add-zsh-hook preexec _cmdlog_preexec
add-zsh-hook precmd _cmdlog_precmd
