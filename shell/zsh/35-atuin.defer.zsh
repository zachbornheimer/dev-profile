# 35-atuin.defer.zsh — atuin history search. Loads after fzf: both bind ^R.

if [[ -x /opt/homebrew/bin/atuin || -x $HOME/.local/bin/atuin ]]; then
	export ATUIN_TMUX_POPUP=false
	export ATUIN_NOBIND=true
	_zsh_eval_cached atuin -- atuin init zsh
	bindkey '^r' atuin-search
	bindkey -M vicmd '^r' atuin-search
	(($+functions[atuin-search])) || function atuin-search { _atuin_search "$@"; }

	# Keep the command path fork-free. One detached writer receives NUL-framed
	# start/end events; command text can contain tabs, newlines, or backslashes.
	# The pty proxy needs its synchronous history id for OSC markers.
	if [[ -z ${ATUIN_PTY_PROXY_ACTIVE-} ]]; then
		zmodload zsh/datetime
		typeset -g __atuin_history_fd=${__atuin_history_fd:-0} __atuin_history_active=0

		_atuin_history_writer() {
			# A history cwd change must not run interactive directory hooks.
			chpwd_functions=()
			unfunction chpwd 2>/dev/null
			local event dir text id="" result duration
			while IFS= read -r -d '' event; do
				case $event in
				start)
					IFS= read -r -d '' dir && IFS= read -r -d '' text || break
					id=""
					builtin cd -- "$dir" || continue
					id=$(ATUIN_SHELL=zsh atuin history start --hook -- "$text" 2>/dev/null)
					;;
				end)
					IFS= read -r -d '' result && IFS= read -r -d '' duration || break
					[[ -n $id ]] && atuin history end --hook --exit "$result" ${duration:+--duration=$duration} -- "$id"
					id=""
					;;
				esac
			done
		}

		# Reloads close the old stream; its writer drains before exiting on EOF.
		((__atuin_history_fd)) && exec {__atuin_history_fd}>&-
		exec {__atuin_history_fd}> >(_atuin_history_writer >/dev/null 2>&1 &!)

		_atuin_preexec() {
			__atuin_preexec_time=$EPOCHREALTIME
			__atuin_history_active=1
			print -rN -- start "$PWD" "$1" >&$__atuin_history_fd
		}

		_atuin_precmd() {
			local result=$? finished=$EPOCHREALTIME duration=""
			((__atuin_history_active)) || return 0
			printf -v duration %.0f $(((finished - __atuin_preexec_time) * 1000000000))
			((duration < 0)) && duration=0
			print -rN -- end "$result" "$duration" >&$__atuin_history_fd
			__atuin_history_active=0
			return 0
		}
	fi
fi
