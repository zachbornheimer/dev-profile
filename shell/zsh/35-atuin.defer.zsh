# 35-atuin.defer.zsh — atuin history search. Loads after fzf: both bind ^R.

if [[ -x /opt/homebrew/bin/atuin || -x $HOME/.local/bin/atuin ]]; then
	export ATUIN_TMUX_POPUP=false
	export ATUIN_NOBIND=true
	_zsh_eval_cached atuin -- atuin init zsh
	bindkey '^r' atuin-search
	bindkey -M vicmd '^r' atuin-search
	(($+functions[atuin-search])) || function atuin-search { _atuin_search "$@"; }

	# Stock _atuin_preexec runs `atuin history start` in $(...): a blocking
	# process (130 ms through the mise shim, 200-350 ms under load) on every
	# command, so every cd paid it. Run start AND end in detached subshells and
	# hand the id over through a file. Skipped under the atuin pty-proxy, which
	# needs ATUIN_HISTORY_ID in the shell for its OSC markers.
	if [[ -z ${ATUIN_PTY_PROXY_ACTIVE-} ]]; then
		zmodload zsh/zselect 2>/dev/null
		typeset -g __atuin_id_file=""
		typeset -g __atuin_end_file="" __atuin_end_exit="" __atuin_end_duration=""

		_atuin_preexec() {
			emulate -L zsh
			__atuin_id_file=${TMPDIR:-/tmp}/atuin-id.$$.$EPOCHREALTIME
			__atuin_preexec_time=${EPOCHREALTIME-}
			(
				id=$(ATUIN_SHELL=zsh atuin history start --hook -- "$1" 2>/dev/null)
				print -rn -- "$id" >|"$__atuin_id_file.tmp" && command mv -f "$__atuin_id_file.tmp" "$__atuin_id_file"
			) >/dev/null 2>&1 </dev/null &!
		}

		# The end-of-command fork waits (below) for the id file; it too starts only
		# once the prompt is up, with the exit status and duration captured here.
		_atuin_precmd() {
			local EXIT="$?" __atuin_precmd_time=${EPOCHREALTIME-}
			[[ -n $__atuin_id_file ]] || return 0
			local duration=""
			if [[ -n $__atuin_preexec_time && -n $__atuin_precmd_time ]]; then
				printf -v duration %.0f $(((__atuin_precmd_time - __atuin_preexec_time) * 1000000000))
				((duration < 0)) && duration=0
			fi
			__atuin_end_file=$__atuin_id_file __atuin_end_exit=$EXIT __atuin_end_duration=$duration
			__atuin_id_file=""
			_p_after_prompt_defer _atuin_history_end
			return 0
		}

		_atuin_history_end() {
			local file=$__atuin_end_file EXIT=$__atuin_end_exit duration=$__atuin_end_duration
			[[ -n $file ]] || return 0
			__atuin_end_file=
			(
				local -i tries=0
				while [[ ! -s $file ]] && ((tries++ < 300)); do zselect -t 10; done
				if [[ -s $file ]]; then
					atuin history end --hook --exit $EXIT ${duration:+--duration=$duration} -- "$(<$file)"
				fi
				command rm -f -- "$file" "$file.tmp"
			) >/dev/null 2>&1 </dev/null &!
		}
	fi
fi
