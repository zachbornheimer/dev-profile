# mise activation with a directory/config-change guard in front of the prompt
# hook: unchanged prompts cost only a few zstat calls, and an edited mise.toml
# applies on the next prompt without a cd.
[[ -o interactive ]] || return 0
command -v mise >/dev/null 2>&1 || return 0
eval "$(mise activate zsh)"

zmodload zsh/stat 2>/dev/null
autoload -Uz add-zsh-hook
typeset -g _DEV_PROFILE_MISE_PWD=$PWD
typeset -g _DEV_PROFILE_MISE_STAMP=0

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

_dev_profile_mise_refresh() {
	_dev_profile_mise_config_stamp
	[[ $PWD == $_DEV_PROFILE_MISE_PWD && $_DEV_PROFILE_MISE_NEW == $_DEV_PROFILE_MISE_STAMP ]] && return
	_DEV_PROFILE_MISE_PWD=$PWD
	_DEV_PROFILE_MISE_STAMP=$_DEV_PROFILE_MISE_NEW
	(($+functions[_mise_hook])) && _mise_hook
}

_dev_profile_mise_config_stamp
_DEV_PROFILE_MISE_STAMP=$_DEV_PROFILE_MISE_NEW
add-zsh-hook -D precmd _mise_hook_precmd 2>/dev/null
add-zsh-hook precmd _dev_profile_mise_refresh
