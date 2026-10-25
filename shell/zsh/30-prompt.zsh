# prompt.zsh — async, transient, context-aware zsh prompt (hand-rolled, zero-dep).
#
# Testability (the reason it's shaped this way): rendering is a PURE function of
# explicit state (_p_* globals) assembled by `prompt::build`, kept separate from the
# I/O that gathers that state (git, the clock, language detection). So you can
# drive every visual variant from simulated state — `p_demo` does exactly that —
# without constructing the real situation. Async git uses native zsh (`zle -F`
# on a process-substitution fd); no gitstatus binary, no plugin.
#
# Color is reserved for meaning, matching kitty: dim by default, amber = needs
# attention (dirty / aws), red = failed / conflict.

zmodload zsh/datetime 2>/dev/null
autoload -Uz add-zsh-hook

typeset -gA _p_c=(
	txt '%F{#c9c9c2}' dim '%F{#6a6a72}' amber '%F{#c2a36b}'
	red '%F{#b9706e}' green '%F{#87a06f}' blue '%F{#7f9cb8}' rst '%f'
)

typeset -g _p_dur_min=2 # show command duration only past this many seconds
typeset -g _p_git="" _p_exit=0 _p_start=0 _p_dur=0 _p_git_fd=0
typeset -g _p_repo_root="" # enclosing git repo (for repo-relative path)
typeset -g _p_aws_seen=0   # show the AWS segment only once you've run an aws command
typeset -g _p_fakepath=""  # demo override for the path segment

# ---- pure helpers (no I/O beyond the filesystem path) -----------------------

# Inside a git repo: show "<repo-name>/<subpath>" (the part above the repo root
# is noise — you live in repos and cd constantly). Elsewhere: the home path with
# parent components abbreviated to their first letter, so depth shows but it
# never eats the line.
prompt::path() {
	local full="${_p_fakepath:-${PWD/#$HOME/~}}"
	if [[ -n $_p_repo_root ]]; then
		local repoH="${_p_repo_root/#$HOME/~}"
		[[ $full == "$repoH" ]] && {
			print -r -- "${repoH:t}"
			return
		}
		[[ $full == "$repoH"/* ]] && {
			print -r -- "${repoH:t}${full#$repoH}"
			return
		}
	fi
	local -a parts=("${(@s:/:)full}") abbr=()
	local n=$#parts i s
	for ((i = 1; i < n; i++)); do
		s="$parts[i]"
		if [[ -z $s || $s == "~" ]]; then
			abbr+=("$s")
		elif [[ $s == .* ]]; then
			abbr+=("${s[1,2]}")
		else abbr+=("${s[1,1]}"); fi
	done
	abbr+=("$parts[n]")
	print -r -- "${(j:/:)abbr}"
}

prompt::fmt-dur() {
	local t=$1
	if ((t < 60)); then
		printf '%.1fs' $t
	elif ((t < 3600)); then
		printf '%dm%02ds' $((t / 60)) $((t % 60))
	else printf '%dh%02dm' $((t / 3600)) $(((t % 3600) / 60)); fi
}

# Build the git segment from explicit fields — the unit-testable core.
prompt::git-segment() { # branch dirty ahead behind stash action
	local branch=$1 dirty=$2 ahead=$3 behind=$4 stash=$5 action=$6
	[[ -z $branch ]] && return
	local col=${_p_c[dim]}
	[[ -n $dirty ]] && col=${_p_c[amber]}
	local seg="${col}${branch}${dirty}${_p_c[rst]}"
	((ahead > 0)) && seg+=" ${_p_c[dim]}↑${ahead}${_p_c[rst]}"
	((behind > 0)) && seg+=" ${_p_c[dim]}↓${behind}${_p_c[rst]}"
	((stash > 0)) && seg+=" ${_p_c[dim]}⚑${stash}${_p_c[rst]}"
	[[ -n $action ]] && seg+=" ${_p_c[red]}${action}${_p_c[rst]}"
	print -r -- "$seg"
}

# Assemble PROMPT/RPROMPT from current state. Pure: reads _p_* only, no I/O.
prompt::build() {
	local line="${_p_c[txt]}$(prompt::path)${_p_c[rst]}"
	[[ -n $_p_git ]] && line+="  $_p_git"
	# AWS profile — shown only once you've actually run an aws command this session
	# (a global AWS_PROFILE=default shouldn't clutter every prompt). Prod shouts red.
	if [[ -n $AWS_PROFILE && $_p_aws_seen == 1 ]]; then
		local awscol=${_p_c[amber]}
		[[ $AWS_PROFILE == (*prod*|*production*|*prd*) ]] && awscol=${_p_c[red]}
		line+="  ${awscol}aws:${AWS_PROFILE}${_p_c[rst]}"
	fi
	local guard=""
	[[ -n $SSH_CONNECTION ]] && guard="${_p_c[dim]}%n@%m${_p_c[rst]} "
	((EUID == 0)) && guard="${_p_c[red]}%n@%m${_p_c[rst]} "
	local mark="${_p_c[dim]}❯${_p_c[rst]}"
	((_p_exit != 0)) && mark="${_p_c[red]}❯${_p_c[rst]}"
	PROMPT="${guard}${line}"$'\n'"${mark} "
	if ((_p_dur >= _p_dur_min)); then
		RPROMPT="${_p_c[dim]}$(prompt::fmt-dur $_p_dur)${_p_c[rst]}"
	else
		RPROMPT=""
	fi
}

# ---- gathering (I/O; kept off the render path) ------------------------------

# Compact git state on one line: branch|dirty|ahead|behind|stash|action.
# Runs in a background subshell, so the porcelain/status cost never blocks.
_p_git_compute() {
	command git rev-parse --is-inside-work-tree &>/dev/null || return
	local branch ahead=0 behind=0 stash=0 action="" dirty="" gd counts
	branch=$(command git symbolic-ref --short -q HEAD 2>/dev/null) ||
		branch=$(command git rev-parse --short HEAD 2>/dev/null)
	[[ -n $(command git status --porcelain --ignore-submodules 2>/dev/null) ]] && dirty="*"
	counts=$(command git rev-list --left-right --count @{upstream}...HEAD 2>/dev/null) &&
		{
			behind=${counts%%[[:space:]]*}
			ahead=${counts##*[[:space:]]}
		}
	stash=$(command git rev-list --walk-reflogs --count refs/stash 2>/dev/null) || stash=0
	gd=$(command git rev-parse --git-dir 2>/dev/null)
	if [[ -d $gd/rebase-merge ]]; then
		action="rebase ${$(<$gd/rebase-merge/msgnum):-?}/${$(<$gd/rebase-merge/end):-?}"
	elif [[ -d $gd/rebase-apply ]]; then
		action="rebase"
	elif [[ -f $gd/MERGE_HEAD ]]; then
		action="merge"
	elif [[ -f $gd/CHERRY_PICK_HEAD ]]; then
		action="cherry-pick"
	elif [[ -f $gd/BISECT_LOG ]]; then
		action="bisect"
	fi
	print -r -- "${branch}|${dirty}|${ahead}|${behind}|${stash}|${action}"
}

_p_async_start() {
	# Widgets read stdin from /dev/null; check editor activity, not terminal input.
	zle || return
	if ((_p_git_fd)); then
		zle -F $_p_git_fd 2>/dev/null
		exec {_p_git_fd}<&-
		_p_git_fd=0
	fi
	exec {_p_git_fd}< <(_p_git_compute)
	zle -F $_p_git_fd _p_async_done
}

_p_async_done() {
	local fd=$1 data
	data="$(<&$fd)"
	zle -F $fd 2>/dev/null
	exec {fd}<&-
	_p_git_fd=0
	if [[ -n $data ]]; then
		local -a f=("${(@s:|:)data}")
		_p_git=$(prompt::git-segment "$f[1]" "$f[2]" "$f[3]" "$f[4]" "$f[5]" "$f[6]")
	else
		_p_git=""
	fi
	prompt::build
	zle reset-prompt
}

# Find the enclosing git repo root on directory change — pure zsh, no subprocess
# on the cd path. Feeds the repo-relative path in prompt::path.
_p_dir_update() {
	_p_git=""
	if ((_p_git_fd)); then
		zle -F $_p_git_fd 2>/dev/null
		exec {_p_git_fd}<&-
		_p_git_fd=0
	fi
	_p_repo_root=""
	local d=$PWD
	while [[ -n $d && $d != / ]]; do
		[[ -e $d/.git ]] && {
			_p_repo_root=$d
			return
		}
		d=${d:h}
	done
}

# ---- hooks ------------------------------------------------------------------

_p_preexec() {
	_p_start=$EPOCHREALTIME
	# Once an AWS command runs, surface the active profile for the rest of the
	# session (the guardrail you want while doing AWS work — but not before).
	case "${1%% *}" in
	aws | aws-vault | awsp | sam | copilot | eb) _p_aws_seen=1 ;;
	esac
}

_p_precmd() {
	_p_exit=$?
	if ((_p_start)); then
		_p_dur=$((EPOCHREALTIME - _p_start))
		_p_start=0
	else _p_dur=0; fi
	prompt::build
}

# Transient: collapse the just-run prompt to "HH:MM ❯" so scrollback is a clean
# timeline instead of the full header repeated on every command.
_p_line_finish() {
	PROMPT="${_p_c[dim]}%D{%H:%M}${_p_c[rst]} ${_p_c[dim]}❯${_p_c[rst]} "
	RPROMPT=""
	zle reset-prompt
}

_p_line_init() {
	((${+functions[_zsh_deferred_init]})) && _zsh_deferred_init
	_p_async_start
}

setopt prompt_subst
add-zsh-hook preexec _p_preexec
add-zsh-hook precmd _p_precmd
add-zsh-hook chpwd _p_dir_update
_p_dir_update
if [[ -o zle && -t 0 ]]; then
	zle -N zle-line-finish _p_line_finish
	zle -N zle-line-init _p_line_init
fi
