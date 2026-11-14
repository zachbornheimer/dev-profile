# 30-prompt.zsh — Starship prompt renderer with live macOS light/dark switching,
# transient timestamp prompt, on-demand AWS context, and project preview URLs.

zmodload zsh/datetime 2>/dev/null
zmodload -F zsh/stat b:zstat 2>/dev/null
autoload -Uz add-zsh-hook

typeset -gA _p_c=()
typeset -g _p_aws_seen=${_p_aws_seen:-0}
typeset -g _p_repo_root=""
typeset -g _p_theme=""
typeset -g _p_prompt_text=""
typeset -g _p_starship_prompt=""
typeset -g _p_prompt_fd=0
typeset -g _p_prompt_dir=""
typeset -gi _p_prompt_cap=${_p_prompt_cap:-2}
typeset -g _p_url_fd=0

_p_apply_theme() {
	local mode=${1:-light}
	_p_theme=$mode
	if [[ $mode == dark ]]; then
		export STARSHIP_CONFIG="$HOME/.config/starship-dark.toml"
		_p_c=(
			txt '%F{#e0def4}'
			dim '%F{#aaa4ba}'
			amber '%F{#f6c177}'
			red '%F{#f28ca5}'
			green '%F{#a1d1ac}'
			blue '%F{#9ccfd8}'
			cyan '%F{#a3dbe5}'
			magenta '%F{#c4a7e7}'
			rst '%f'
		)
	else
		export STARSHIP_CONFIG="$HOME/.config/starship.toml"
		_p_c=(
			txt '%F{#303436}'
			dim '%F{#59646a}'
			amber '%F{#86540e}'
			red '%F{#a22d37}'
			green '%F{#33683b}'
			blue '%F{#285a83}'
			cyan '%F{#24636b}'
			magenta '%F{#7a5080}'
			rst '%f'
		)
	fi
}

typeset -gi _p_theme_plist_mtime=-1
_p_sync_theme() {
	local mode="light" plist="$HOME/Library/Preferences/.GlobalPreferences.plist"
	local -a st
	if [[ -n ${ZSH_THEME_MODE:-} ]]; then
		mode=${ZSH_THEME_MODE:l}
	else
		# The OS appearance only changes when this plist is rewritten: skip the
		# `defaults` fork (15-90ms per prompt) until its mtime moves. TRAPWINCH
		# resets the mark, so a theme switch signal always re-reads.
		zstat -A st +mtime -- "$plist" 2>/dev/null
		[[ -n $_p_theme && ${st[1]:--2} == "$_p_theme_plist_mtime" ]] && return 0
		_p_theme_plist_mtime=${st[1]:--2}
		[[ $(defaults read -g AppleInterfaceStyle 2>/dev/null) == *Dark* ]] && mode="dark"
	fi
	_p_apply_theme "$mode"
}

# Find the enclosing git repo root on directory change (pure zsh, no subprocess).
_p_dir_update() {
	unset HYBRID_PREVIEW_URL
	if ((_p_url_fd)); then
		zle -F $_p_url_fd 2>/dev/null
		exec {_p_url_fd}<&-
		_p_url_fd=0
	fi
	_p_repo_root=""
	local d=$PWD
	while [[ -n $d && $d != / ]]; do
		if [[ -e $d/.git ]]; then
			_p_repo_root=$d
			return 0
		fi
		d=${d:h}
	done
}

# Starship renders in the background under a hard cap; PROMPT only ever prints
# the text this shell already has, so a slow repository (or a hung git) delays
# the git/status segment but never the keypress path.
_p_starship_args() {
	reply=(
		--terminal-width="$COLUMNS"
		--keymap="${KEYMAP:-}"
		--status="${STARSHIP_CMD_STATUS:-}"
		--pipestatus="${STARSHIP_PIPE_STATUS[*]:-}"
		--cmd-duration="${STARSHIP_DURATION:-}"
		--jobs="${STARSHIP_JOBS_COUNT:-0}"
	)
}

_p_prompt_cancel() {
	((_p_prompt_fd)) || return 0
	zle -F "$_p_prompt_fd" 2>/dev/null
	exec {_p_prompt_fd}<&-
	_p_prompt_fd=0
}

_p_prompt_collect() {
	local -i fd=$1
	local out=""
	read -t 1 -u "$fd" -r -d '' out 2>/dev/null
	print -rn -- "$out"
}

# The full header, git modules included: the only render that may be slow.
_p_render_full() {
	local -a args command
	local cap=${_p_prompt_cap}s
	_p_starship_args
	args=("$@")
	# The cap is part of the wrapper; with no timeout binary the render runs
	# uncapped rather than failing.
	if ((${+commands[timeout]})); then
		command=("${commands[timeout]}" -k 1 "$cap")
	elif ((${+commands[gtimeout]})); then
		command=("${commands[gtimeout]}" -k 1 "$cap")
	fi
	[[ -n $_p_starship_bin ]] || return 1
	"${command[@]}" "$_p_starship_bin" prompt "${args[@]}"
}

# Bookkeeping the prompt does not need (`zoxide add`, `dev-profile-enter`,
# `atuin history end`, and every starship render). Each is a fork
# of this large shell: ~1ms idle, 15-110ms when the machine is busy, so none may
# run before the prompt is painted. A hook calls `_p_after_prompt_defer FN`; FN
# runs once, from a `zle -F` handler on an always-readable fd, which zle only
# services after it has drawn the prompt. Keep this fd open between prompts:
# reopening it can synchronously run process-substitution cleanup. Outside an interactive tty (scripts,
# tests) FN runs at once.
typeset -ga _p_after_prompt_fns=()
typeset -gi _p_after_prompt_fd=0

_p_after_prompt_defer() {
	if [[ ! -o zle || ! -t 0 ]]; then
		((${+functions[$1]})) && "$1"
		return 0
	fi
	((${_p_after_prompt_fns[(Ie)$1]})) || _p_after_prompt_fns+=("$1")
	if ((!_p_after_prompt_fd)); then
		exec {_p_after_prompt_fd}</dev/null || return 0
	fi
	zle -F $_p_after_prompt_fd _p_after_prompt_run
}

_p_after_prompt_run() {
	local -i fd=$1
	local fn
	local -a fns=("${_p_after_prompt_fns[@]}")
	zle -F $fd 2>/dev/null
	_p_after_prompt_fns=()
	for fn in "${fns[@]}"; do
		((${+functions[$fn]})) && "$fn"
	done
	return 0
}

# Paint now, finish the render in the background. A directory change never
# waits on starship: the prompt shows a header built in pure zsh (no fork) and
# the full render, git modules included, repaints it through _p_prompt_ready.
# Same-directory prompts keep the cached header until the new render arrives.
_p_prompt_request() {
	[[ -n $_p_starship_bin ]] || return 0
	local out dir=$PWD
	_p_prompt_cancel
	if [[ ! -o zle || ! -t 0 ]]; then
		out=$(_p_render_full)
		[[ -n $out ]] && _p_prompt_text=$out
		_p_prompt_dir=$dir
		return 0
	fi
	if [[ $dir != "$_p_prompt_dir" || -z $_p_prompt_text ]]; then
		_p_prompt_text="${_p_c[cyan]}%B%~%b${_p_c[rst]}"$'\n'"${_p_c[green]}❯${_p_c[rst]} "
	fi
	_p_prompt_dir=$dir
	_p_after_prompt_defer _p_prompt_render_start
	return 0
}

# Started after the prompt is up, on both cd and same-directory prompts.
_p_prompt_render_start() {
	_p_prompt_cancel
	_p_prompt_dir=$PWD
	exec {_p_prompt_fd}< <(_p_render_full 2>/dev/null)
	((_p_prompt_fd)) && zle -F "$_p_prompt_fd" _p_prompt_ready
}

# A finished background render: paint it if the directory still holds and no
# newer render replaced it.
_p_prompt_ready() {
	local -i fd=$1
	local dir=$_p_prompt_dir
	local out=""
	if ((fd == _p_prompt_fd)); then
		out=$(_p_prompt_collect "$_p_prompt_fd")
		_p_prompt_cancel
	else
		zle -F "$fd" 2>/dev/null
		exec {fd}<&-
	fi
	if [[ -n $out && $PWD == "$dir" && $out != "$_p_prompt_text" ]]; then
		_p_prompt_text=$out
		zle reset-prompt 2>/dev/null
	fi
}

# Re-render and repaint: for a change the cached line cannot show by itself
# (new terminal width, preview URL, directory).
_p_redraw() {
	_p_prompt_request
	zle reset-prompt 2>/dev/null
}

# A cd from a ZLE widget (fzf's alt-c) leaves a prompt for the old directory.
_p_prompt_chpwd() {
	zle || return 0
	_p_redraw
}

_p_sync_aws() {
	unset HYBRID_AWS_SAFE HYBRID_AWS_PROD
	if [[ -n ${AWS_PROFILE:-} && ${_p_aws_seen:-0} == 1 ]]; then
		if [[ $AWS_PROFILE == (*prod*|*production*|*prd*) ]]; then
			export HYBRID_AWS_PROD=$AWS_PROFILE
		else
			export HYBRID_AWS_SAFE=$AWS_PROFILE
		fi
	fi
}

# The preview URL is looked up by _p_url_async_start, off the prompt path. The
# lookup reads pidfiles and forks (sed, kill, jq, lsof): 20-150ms of every
# prompt in a repo when it ran here. A cd already cleared the old URL in
# _p_dir_update, so all this owes the prompt is the unset outside a repo.
_p_sync_preview() {
	if [[ -z $_p_repo_root || ${ZSH_PROMPT_STYLE:-colorful} == classic ]]; then
		unset HYBRID_PREVIEW_URL
	fi
}

_p_url_async_start() {
	zle || return 0
	[[ -n $_p_repo_root && ${ZSH_PROMPT_STYLE:-colorful} != classic ]] || return 0
	((${+functions[preview::selected-urls]})) || return 0
	if ((_p_url_fd)); then
		zle -F $_p_url_fd 2>/dev/null
		exec {_p_url_fd}<&-
		_p_url_fd=0
	fi
	exec {_p_url_fd}< <(preview::selected-urls "$_p_repo_root")
	zle -F $_p_url_fd _p_url_async_done
}

_p_url_async_done() {
	local fd=$1 data=""
	data="$(<&$fd)"
	zle -F "$fd" 2>/dev/null
	exec {fd}<&-
	_p_url_fd=0
	local formatted="${data//$'\n'/ · }"
	if [[ $formatted != "${HYBRID_PREVIEW_URL:-}" ]]; then
		if [[ -n $formatted ]]; then
			export HYBRID_PREVIEW_URL=$formatted
		else
			unset HYBRID_PREVIEW_URL
		fi
		_p_redraw
	fi
}

_p_preexec() {
	case "${1%% *}" in
	aws | aws-vault | awsp | sam | copilot | eb) _p_aws_seen=1 ;;
	esac
}

_p_precmd() {
	_p_sync_theme
	_p_sync_aws
	_p_sync_preview
	_p_prompt_request
	[[ -n $_p_starship_prompt ]] && PROMPT=$_p_starship_prompt
	RPROMPT=""
}

# Transient: collapse the just-run prompt to "HH:MM ❯" so scrollback stays clean.
_p_line_finish() {
	PROMPT="${_p_c[dim]}%D{%H:%M}${_p_c[rst]} ${_p_c[dim]}❯${_p_c[rst]} "
	RPROMPT=""
	zle reset-prompt
}

_p_line_init() {
	# Prompt is ready: close the cd-latency measurement before anything else runs.
	((${+functions[_cdlat_line_init]})) && _cdlat_line_init
	((${+functions[_zsh_deferred_init]})) && _zsh_deferred_init
	_p_url_async_start
}

# Re-sync appearance and redraw when signaled (e.g. by set-theme.sh on OS switch).
# The cached header has the old width, so a resize is also a re-render.
TRAPWINCH() {
	_p_theme_plist_mtime=-1
	_p_sync_theme
	zle && _p_redraw
}
if [[ -n ${ZSH_THEME_MODE:-} ]] || ((${+functions[defaults]})) ||
	[[ ! -s $HOME/.config/borders/current-theme ]] ||
	[[ $HOME/Library/Preferences/.GlobalPreferences.plist -nt $HOME/.config/borders/current-theme ]]; then
	_p_sync_theme
else
	_p_apply_theme "$(<"$HOME/.config/borders/current-theme")"
fi

typeset -g _p_starship_bin=""
if [[ -x /opt/homebrew/bin/starship ]]; then
	_p_starship_bin=/opt/homebrew/bin/starship
elif ((${+commands[starship]})); then
	_p_starship_bin=${commands[starship]}
fi

if [[ -n $_p_starship_bin ]]; then
	if ((!${+functions[prompt_starship_precmd]})); then
		zmodload zsh/parameter zsh/datetime zsh/mathfunc 2>/dev/null
		__starship_get_time() {
			((STARSHIP_CAPTURED_TIME = int(rint(EPOCHREALTIME * 1000))))
		}
		prompt_starship_precmd() {
			STARSHIP_CMD_STATUS=$? STARSHIP_PIPE_STATUS=(${pipestatus[@]})
			if ((${+STARSHIP_START_TIME})); then
				__starship_get_time && STARSHIP_DURATION=$((STARSHIP_CAPTURED_TIME - STARSHIP_START_TIME))
				unset STARSHIP_START_TIME
			else
				unset STARSHIP_DURATION STARSHIP_CMD_STATUS STARSHIP_PIPE_STATUS
			fi
			STARSHIP_JOBS_COUNT="${#jobstates[*]}"
		}
		prompt_starship_preexec() {
			__starship_get_time && STARSHIP_START_TIME=$STARSHIP_CAPTURED_TIME
		}
		starship_zle-keymap-select() { zle reset-prompt; }
		[[ -o zle ]] && zle -N zle-keymap-select starship_zle-keymap-select
		add-zsh-hook precmd prompt_starship_precmd
		add-zsh-hook preexec prompt_starship_preexec
		export STARSHIP_SHELL="zsh"
		printf -v STARSHIP_SESSION_KEY '%08x%08x' $((RANDOM * 65536 + RANDOM)) $((EPOCHSECONDS * 65536 + RANDOM))
		export STARSHIP_SESSION_KEY=${STARSHIP_SESSION_KEY:0:16}
		VIRTUAL_ENV_DISABLE_PROMPT=1
	fi
	# Only ever the text this shell already has: the render happens in
	# _p_prompt_request, never on the keypress path.
	PROMPT='${_p_prompt_text}'
	PROMPT2='$('"$_p_starship_bin"' prompt --continuation)'
	typeset -g STARSHIP_JOBS_COUNT=${STARSHIP_JOBS_COUNT:-0}
	_p_starship_prompt=$PROMPT
	RPROMPT=""
fi

setopt prompt_subst
add-zsh-hook chpwd _p_prompt_chpwd
add-zsh-hook -D preexec _p_preexec 2>/dev/null
add-zsh-hook -D precmd _p_precmd 2>/dev/null
add-zsh-hook -D chpwd _p_dir_update 2>/dev/null
add-zsh-hook preexec _p_preexec
add-zsh-hook precmd _p_precmd
add-zsh-hook chpwd _p_dir_update
_p_dir_update
add-zsh-hook -D chpwd _p_prompt_chpwd 2>/dev/null

if [[ -o zle && -t 0 ]]; then
	zle -N zle-line-finish _p_line_finish
	zle -N zle-line-init _p_line_init
fi
