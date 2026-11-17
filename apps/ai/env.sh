#!/usr/bin/env bash
# Sourced by shell startup files; preserve the caller's shell options.
ai-env::load() {
	local keys_env="$HOME/.cache/ai/keys.env"
	local template="$HOME/.config/ai/keys.env.op"

	# A cache on disk is usable whether or not it is current: source it first, so a non-interactive
	# shell (relay's `bash -l` launch, a script, a CI step) keeps the keys it already has.
	[[ -r "$keys_env" ]] && builtin source "$keys_env"
	[[ -r "$keys_env" && "$keys_env" -nt "$template" ]] && return 0

	# Refreshing needs a human at a 1Password prompt. A non-interactive shell must never wait on one,
	# and must never print the failure onto the stdout its caller reads as data: relay captures
	# session stdout, and one profile line broke an exact-output test (ZYS-9643). Interactive shells
	# and interactive-only tooling still resolve the keys.
	[[ $- == *i* ]] || return 0

	local zsh_bin
	zsh_bin="$(command -v zsh)" || return 0
	keys_env="$("$zsh_bin" -fc 'builtin source "$HOME/.config/zsh/ai-keys.zsh"; ai-keys::env')" || return 1
	builtin source "$keys_env"
}

ai-env::load
