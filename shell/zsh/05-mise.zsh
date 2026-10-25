# 05-mise.zsh — source the Dev Profile's generated mise shell init.
# The profile owns activation and the PWD/config-mtime refresh guard; the
# fallback keeps this module usable before the profile is generated.
if [[ -o interactive ]]; then
	if [[ -r "$HOME/.local/share/dev-profile/mise.zsh" ]]; then
		source "$HOME/.local/share/dev-profile/mise.zsh"
	elif (($+commands[mise])); then
		eval "$(mise activate zsh)"
	fi
fi
