# mise activation with a directory/config-change guard in front of the prompt
# hook: unchanged prompts cost only a few zstat calls, and an edited mise.toml
# applies on the next prompt without a cd.
#
# Nothing here forks on the cd or the prompt path. `mise hook-env` (and direnv's
# `export`, see 40-direnv.defer.zsh) runs in the background and its output is
# eval'd by a `zle -F` handler once it arrives, so a slow exec costs a late
# environment, never a late prompt.
[[ -o interactive ]] || return 0
command -v mise >/dev/null 2>&1 || return 0
eval "$(mise activate zsh)"

zmodload zsh/stat 2>/dev/null
autoload -Uz add-zsh-hook

# _dev_profile_async_eval NAME FN: run FN (a function printing shell code) in the
# background, then eval its output here. One run per NAME at a time; a request
# made while one is in flight re-runs FN once it lands, so the last directory
# always wins.
typeset -gA _DEV_PROFILE_ASYNC_FD _DEV_PROFILE_ASYNC_FN _DEV_PROFILE_ASYNC_PENDING

_dev_profile_async_eval() {
	local name=$1 fn=$2 fd
	if ((${_DEV_PROFILE_ASYNC_FD[$name]:-0})); then
		_DEV_PROFILE_ASYNC_PENDING[$name]=1
		return 0
	fi
	exec {fd}< <($fn)
	_DEV_PROFILE_ASYNC_FD[$name]=$fd
	_DEV_PROFILE_ASYNC_FN[$name]=$fn
	zle -F $fd _dev_profile_async_apply 2>/dev/null
}

# Handler for `zle -F` (and the synchronous drain below): read the finished
# job's output, eval it, then start the queued re-run or repaint the prompt.
_dev_profile_async_apply() {
	local fd=$1 key name= line out= fn
	for key in ${(k)_DEV_PROFILE_ASYNC_FD}; do
		[[ ${_DEV_PROFILE_ASYNC_FD[$key]} == $fd ]] && name=$key
	done
	[[ -n $name ]] || return 0
	zle -F $fd 2>/dev/null
	while IFS= read -r -u $fd line || [[ -n $line ]]; do
		out+=$line$'\n'
	done
	exec {fd}<&-
	_DEV_PROFILE_ASYNC_FD[$name]=0
	fn=${_DEV_PROFILE_ASYNC_FN[$name]}
	[[ -n $out ]] && eval "$out"
	if ((${_DEV_PROFILE_ASYNC_PENDING[$name]:-0})); then
		_DEV_PROFILE_ASYNC_PENDING[$name]=0
		_dev_profile_async_eval $name $fn
	elif [[ -n $out ]]; then
		zle reset-prompt 2>/dev/null
	fi
	return 0
}

# Block until every background job has landed (tests, scripts; not the prompt).
_dev_profile_async_wait() {
	local key busy=1
	while ((busy)); do
		busy=0
		for key in ${(k)_DEV_PROFILE_ASYNC_FD}; do
			if ((${_DEV_PROFILE_ASYNC_FD[$key]})); then
				busy=1
				_dev_profile_async_apply ${_DEV_PROFILE_ASYNC_FD[$key]}
			fi
		done
	done
}

# The real binary, not the shim: a shim is itself a slow exec.
typeset -g _DEV_PROFILE_MISE_BIN= _dp_dir
for _dp_dir in /opt/homebrew/bin "$HOME/.local/bin" /usr/local/bin; do
	[[ -x $_dp_dir/mise ]] && _DEV_PROFILE_MISE_BIN=$_dp_dir/mise && break
done
[[ -n $_DEV_PROFILE_MISE_BIN ]] || _DEV_PROFILE_MISE_BIN=${commands[mise]}
unset _dp_dir

typeset -g _DEV_PROFILE_MISE_PWD=$PWD
typeset -g _DEV_PROFILE_MISE_STAMP=0
typeset -g _DEV_PROFILE_MISE_REASON=precmd

_dev_profile_mise_config_stamp() {
	local dir=$PWD file newest=0
	local -a statbuf
	while :; do
		for file in "$dir"/mise.toml "$dir"/.mise.toml "$dir"/mise.local.toml; do
			[[ -f $file ]] || continue
			zstat -A statbuf +mtime -- "$file" 2>/dev/null || continue
			((statbuf[1] > newest)) && newest=$statbuf[1]
		done
		[[ $dir == / ]] && break
		dir=${dir:h}
	done
	for file in "$HOME"/.config/mise/config.toml "$HOME"/.config/mise/conf.d/*.toml(N); do
		[[ -f $file ]] || continue
		zstat -A statbuf +mtime -- "$file" 2>/dev/null || continue
		((statbuf[1] > newest)) && newest=$statbuf[1]
	done
	typeset -g _DEV_PROFILE_MISE_NEW=$newest
}

_dev_profile_mise_run() {
	command "$_DEV_PROFILE_MISE_BIN" hook-env --shell-pid $$ -s zsh \
		--reason $_DEV_PROFILE_MISE_REASON 2>/dev/null
}

# Precmd and chpwd both land here: the stamp guard makes an unchanged prompt a
# few zstat calls, and a changed directory or edited mise.toml starts one
# background hook-env.
_dev_profile_mise_refresh() {
	_dev_profile_mise_config_stamp
	[[ $PWD == $_DEV_PROFILE_MISE_PWD && $_DEV_PROFILE_MISE_NEW == $_DEV_PROFILE_MISE_STAMP ]] && return
	if [[ $PWD == $_DEV_PROFILE_MISE_PWD ]]; then
		_DEV_PROFILE_MISE_REASON=precmd
	else
		_DEV_PROFILE_MISE_REASON=chpwd
	fi
	_DEV_PROFILE_MISE_PWD=$PWD
	_DEV_PROFILE_MISE_STAMP=$_DEV_PROFILE_MISE_NEW
	_dev_profile_async_eval mise _dev_profile_mise_run
}

_dev_profile_mise_config_stamp
_DEV_PROFILE_MISE_STAMP=$_DEV_PROFILE_MISE_NEW
add-zsh-hook -D precmd _mise_hook_precmd 2>/dev/null
add-zsh-hook -D chpwd _mise_hook_chpwd 2>/dev/null
add-zsh-hook precmd _dev_profile_mise_refresh
add-zsh-hook chpwd _dev_profile_mise_refresh
