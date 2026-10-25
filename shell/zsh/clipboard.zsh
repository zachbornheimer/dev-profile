# Sets `reply` to the clipboard copy command; returns 1 when no tool exists.
clipboard::copy-cmd() {
	if (($+commands[pbcopy])); then
		reply=(pbcopy)
	elif (($+commands[xclip])); then
		reply=(xclip -selection clipboard)
	elif (($+commands[xsel])); then
		reply=(xsel --clipboard --input)
	else
		return 1
	fi
}

cb2f() {
	emulate -L zsh

	local target_file="$1"
	local overwrite=false
	local -a clip_cmd

	if [[ -z $target_file ]]; then
		__ -t failed "usage: cb2f <file> [--overwrite]"
		return 2
	fi

	if (($+commands[pbpaste])); then
		clip_cmd=(pbpaste)
	elif (($+commands[xclip])); then
		clip_cmd=(xclip -selection clipboard -out)
	elif (($+commands[xsel])); then
		clip_cmd=(xsel --clipboard --output)
	else
		__ -t failed "cb2f: no supported clipboard tool found (pbpaste, xclip, xsel)"
		return 1
	fi

	[[ "${2:-}" == "--overwrite" ]] && overwrite=true

	if [[ -f $target_file && $overwrite != true ]]; then
		printf 'Do you want to overwrite? [Y/n] '
		local response
		read -r response
		if [[ -n $response && ! $response =~ ^[Yy]$ ]]; then
			__ -o stdout -t warn "Aborted. File was not written."
			return 0
		fi
	fi

	local content
	content="$("${clip_cmd[@]}")"

	if ! print -r -- "$content" >"$target_file" 2>/dev/null; then
		__ -t failed "cb2f: could not write to $target_file"
		return 1
	fi

	local short_content
	short_content="$(printf '%s' "$content" | head -c 100)"
	__ -t success "Wrote $target_file with \"${short_content}\""
}

cx() {
	emulate -L zsh

	local target_file="$1"
	local -a clip_cmd

	if [[ -z $target_file ]]; then
		__ -t failed "usage: cx <file>"
		return 2
	fi

	if [[ ! -f $target_file ]]; then
		__ -t failed "cx: file not found: $target_file"
		return 1
	fi

	clipboard::copy-cmd || {
		__ -t failed "cx: no supported clipboard tool found (pbcopy, xclip, xsel)"
		return 1
	}
	clip_cmd=($reply)

	if ! "${clip_cmd[@]}" <"$target_file"; then
		__ -t failed "cx: could not copy $target_file to the clipboard"
		return 1
	fi

	__ -t success "Copied $target_file to clipboard"
}

# Copy a command to clipboard (path sensitive)
cxc() {
	if [ $# -eq 0 ]; then
		__ -t failed "Usage: cxc <command...>"
		return 1
	fi

	# Directory where cxc is invoked
	local dir="$PWD"

	# Safely reconstruct the command with proper quoting
	local cmd
	cmd=$(printf '%q ' "$@")
	cmd=${cmd% } # trim trailing space

	# Pasted snippet:
	# 1. Save current dir
	# 2. cd into the original cxc dir
	# 3. run the command
	# 4. cd back, then unset the temp var
	local snippet='_cxc_oldpwd=$(pwd); cd '"$dir"' && '"$cmd"'; cd "$_cxc_oldpwd"; unset _cxc_oldpwd'

	# Cross‑platform clipboard: macOS, X11, Wayland, Windows (WSL/git-bash)
	if command -v pbcopy >/dev/null 2>&1; then
		printf '%s' "$snippet" | pbcopy
		__ -t success "Copied command to clipboard."
	elif command -v xclip >/dev/null 2>&1; then
		printf '%s' "$snippet" | xclip -selection clipboard
		__ -t success "Copied command to clipboard."
	elif command -v wl-copy >/dev/null 2>&1; then
		printf '%s' "$snippet" | wl-copy
		__ -t success "Copied command to clipboard."
	elif command -v clip.exe >/dev/null 2>&1; then
		printf '%s' "$snippet" | clip.exe
		__ -t success "Copied command to clipboard."
	else
		echo "$snippet"
		__ -o stdout -t warn "No clipboard utility found; printed command instead."
	fi
}

alias cbwrite=cb2f
alias uuid="uuidgen | tr -d '\n' | tr '[:upper:]' '[:lower:]'  | pbcopy && pbpaste && echo"
alias cb2l='pbpaste | paste -sd\s - | perl -ple "s/\s+/ /g" | pbcopy; __ -t success "Compressed clipboard to 1 line."'
alias cpwd="pwd | pbcopy"
