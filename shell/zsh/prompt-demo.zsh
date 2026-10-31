# prompt-demo.zsh — p_demo: renders Starship prompt variants (light/dark, status, duration, AWS, preview URL, transient).

p_demo() {
	emulate -L zsh
	local width=${COLUMNS:-80}
	print -P -- "%B── Starship prompt variants (${_p_theme:-light} theme) ─────────────────────────%b"
	print
	print -P -- "%B1. Clean command (exit 0)%b"
	print -P -- "$(env -u HYBRID_AWS_SAFE -u HYBRID_AWS_PROD -u HYBRID_PREVIEW_URL \
		starship prompt --terminal-width="$width" --status=0 --jobs=0)"
	print
	print -P -- "%B2. Failed command (exit 1) + duration (8.2s)%b"
	print -P -- "$(env -u HYBRID_AWS_SAFE -u HYBRID_AWS_PROD -u HYBRID_PREVIEW_URL \
		starship prompt --terminal-width="$width" --status=1 --cmd-duration=8200 --jobs=0)"
	print
	print -P -- "%B3. AWS production profile + project preview URL%b"
	print -P -- "$(env -u HYBRID_AWS_SAFE HYBRID_AWS_PROD=prod HYBRID_PREVIEW_URL="https://app.localhost" \
		starship prompt --terminal-width="$width" --status=0 --jobs=0)"
	print
	print -P -- "%B4. Transient prompt (collapsed past command)%b"
	print -P -- "${_p_c[dim]}14:23${_p_c[rst]} ${_p_c[dim]}❯${_p_c[rst]} make build"
	print
}
