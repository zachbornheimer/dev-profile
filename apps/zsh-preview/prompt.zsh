# Preview route integration for Starship; enabled by ~/.zshrc.local and ~/.config/zsh-preview/.zshrc.
# Starship is the single prompt renderer — this module loads route discovery (routes.zsh)
# and syncs HYBRID_PREVIEW_URL without registering competing prompt hooks.

typeset -gA _p_c
typeset -g _preview_url="" _preview_project=""

builtin source "$HOME/.config/zsh-preview/routes.zsh"

if ((!$#_p_c)); then
	if ((${+functions[_p_sync_theme]})); then
		_p_sync_theme
	else
		_p_c[cyan]='%F{#89dceb}'
		_p_c[magenta]='%F{#f5a0d5}'
		_p_c[amber]='%F{#f9e2af}'
		_p_c[red]='%F{#f38ba8}'
		_p_c[green]='%F{#a6e3a1}'
		_p_c[blue]='%F{#89b4fa}'
		_p_c[dim]='%F{#6a6a72}'
		_p_c[txt]='%F{#c9c9c2}'
		_p_c[rst]='%f'
	fi
fi

preview::width() {
	emulate -L zsh
	setopt extendedglob
	local visible=${(%)1}
	visible=${visible//$'\e'\[[0-9\;:]#m/}
	print -r -- "${(m)#visible}"
}

preview::header() {
	local left=$1 right=$2
	[[ -n $right ]] || {
		print -r -- "$left"
		return
	}
	local -i left_width=$(preview::width "$left")
	local -i right_width=$(preview::width "$right")
	local -i gap=$((COLUMNS - left_width - right_width - 1))
	if ((gap >= 2)); then
		print -r -- "$left${(pl:gap:: :)}$right"
	else
		print -r -- "$left"$'\n'"$right"
	fi
}
