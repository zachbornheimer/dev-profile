#!/usr/bin/env bash
# Sourced by shell startup files; preserve the caller's shell options.
ai-env::load() {
	local keys_env="$HOME/.cache/ai/keys.env"
	local template="$HOME/.config/ai/keys.env.op"

	local zsh_bin
	zsh_bin="$(command -v zsh)" || zsh_bin=""

	if [[ ! -r "$keys_env" || ! "$keys_env" -nt "$template" ]]; then
		# No zsh (Linux boxes): keys arrive through the environment instead.
		[[ -n "$zsh_bin" ]] || return 0
		keys_env="$("$zsh_bin" -fc 'builtin source "$HOME/.config/zsh/ai-keys.zsh"; ai-keys::env')" || return 1
	fi

	builtin source "$keys_env"
}

ai-env::load
