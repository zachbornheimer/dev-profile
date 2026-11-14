# 50-enter-converge.defer.zsh — on cd, hand the directory to a background worker.
#
# The interactive path does exactly one thing: queue `dev-profile-enter` to be
# forked once the prompt is up (_p_after_prompt_defer, 30-prompt.zsh), then
# return. Everything slow or surprising — mise deps, node_modules, the portless
# proxy — happens in that worker, which serialises one run per checkout and
# never prompts. `cd` only records PWD; even PATH and marker checks are detached. It never starts the dev
# stack; `mise run dev` does that, on request only.
#
# Disable: DEV_PROFILE_ENTER_DISABLE=1 (the old MISE_ENTER_CONVERGE=0 too).

autoload -Uz add-zsh-hook

_enter_converge_enabled() {
	emulate -L zsh
	[[ ${DEV_PROFILE_ENTER_DISABLE:-0} == 1 ]] && return 1
	[[ ${MISE_ENTER_CONVERGE-} == 0 ]] && return 1
	(($+commands[dev-profile-enter]))
}

# Cheap gate: file tests are builtins, so a directory with no marker costs
# nothing. Only the .gitmodules case needs git, and that forks in the detached
# subshell, never on the cd path. The worker proves the rest (git root, serve
# command) for itself.
_enter_converge_has_marker() {
	emulate -L zsh
	local d="${1:-.}"
	[[ -f $d/mise.toml || -f $d/.mise.toml || -f $d/package.json ||
		-f $d/pyproject.toml || -f $d/go.mod || -f $d/composer.json ||
		-f $d/Gemfile || -f $d/aube-lock.yaml || -f $d/uv.lock ]]
}

_enter_converge_start() {
	local d=$_enter_converge_dir
	_enter_converge_dir=
	_enter_converge_worker "$d" >/dev/null 2>&1 </dev/null &!
}

_enter_converge_worker() {
	local d=$1
	_enter_converge_enabled || return 0
	[[ -n $d && -d $d ]] || return 0
	if _enter_converge_has_marker "$d"; then
		exec dev-profile-enter "$d"
	elif [[ -f $d/.gitmodules ]]; then
		builtin cd -q -- "$d" && git rev-parse --is-inside-work-tree >/dev/null 2>&1 && exec dev-profile-enter "$d"
	fi
}

typeset -g _enter_converge_dir=
_enter_converge_chpwd() {
	_enter_converge_dir=$PWD
	_p_after_prompt_defer _enter_converge_start
}

add-zsh-hook -D chpwd _enter_converge_chpwd 2>/dev/null
add-zsh-hook chpwd _enter_converge_chpwd
