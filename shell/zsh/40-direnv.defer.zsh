# 40-direnv.defer.zsh — direnv export starts after the prompt is painted.
# Environment changes land through the shared mise async evaluator.

[[ -x /opt/homebrew/bin/direnv || -x $HOME/.local/bin/direnv ]] || return 0
typeset -g _DEV_PROFILE_DIRENV_BIN
_DEV_PROFILE_DIRENV_BIN="$(_zsh_binpath direnv)" || return 0

_dev_profile_direnv_run() {
	command "$_DEV_PROFILE_DIRENV_BIN" export zsh
}

_dev_profile_direnv_start() {
	if ((${+functions[_dev_profile_async_eval]})); then
		_dev_profile_async_eval direnv _dev_profile_direnv_run
	elif [[ ! -o zle || ! -t 0 ]]; then
		eval "$(_dev_profile_direnv_run)"
	fi
}

_dev_profile_direnv_hook() {
	[[ -o interactive && $ZSH_SUBSHELL -eq 0 ]] || return 0
	if [[ -o zle && -t 0 ]]; then
		((${+functions[_p_after_prompt_defer]})) &&
			_p_after_prompt_defer _dev_profile_direnv_start
	else
		_dev_profile_direnv_start
	fi
	return 0
}

# A prompt only needs an export for an active environment or an enclosing .envrc.
_dev_profile_direnv_precmd() {
	local dir=$PWD
	if [[ -z ${DIRENV_DIR:-} ]]; then
		while [[ -n $dir && $dir != / ]]; do
			[[ -f $dir/.envrc ]] && break
			dir=${dir:h}
		done
		[[ -f $dir/.envrc ]] || return 0
	fi
	_dev_profile_direnv_hook
}

autoload -Uz add-zsh-hook
add-zsh-hook -D precmd _direnv_hook 2>/dev/null
add-zsh-hook -D chpwd _direnv_hook 2>/dev/null
add-zsh-hook precmd _dev_profile_direnv_precmd
add-zsh-hook chpwd _dev_profile_direnv_hook
_dev_profile_direnv_precmd
