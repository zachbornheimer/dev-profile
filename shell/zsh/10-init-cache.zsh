# 10-init-cache.zsh — cached tool-init helpers (_zsh_eval_cached) used by the deferred modules.
# Stale caches keep serving the old file and are rewritten in the background
# for the next shell (&! — the rewrite must not mutate this shell).

typeset -g _ZSH_INIT_CACHE="${XDG_CACHE_HOME:-$HOME/.cache}/zsh/init"
[[ -d $_ZSH_INIT_CACHE ]] || mkdir -p "$_ZSH_INIT_CACHE"

_zsh_binpath() {
	emulate -L zsh
	local name="$1"
	if [[ $name == /* ]]; then
		[[ -x $name ]] && print -r -- "$name" && return 0
		return 1
	fi
	local p dir
	for dir in /opt/homebrew/bin "$HOME/.local/bin" /usr/local/bin; do
		[[ -x $dir/$name ]] && print -r -- "$dir/$name" && return 0
	done
	p="${commands[$name]}"
	[[ -n $p && -x $p ]] && print -r -- "$p" && return 0
	return 1
}

typeset -g _zsh_fast_session_id
printf -v _zsh_fast_session_id '%08x%08x%08x%08x' \
	$((RANDOM * 65536 + RANDOM)) $((RANDOM * 65536 + RANDOM)) \
	$((RANDOM * 65536 + RANDOM)) $((EPOCHSECONDS * 65536 + RANDOM))

# Generated text that runs a tool on every cd/prompt must name the real binary:
# a bare `zoxide` resolves to the mise shim (~0.7-0.9s per call, blocking cd).
_zsh_init_cache_postprocess() {
	emulate -L zsh
	local name="$1" cache="$2" bin="$3"
	case $name in
	atuin) sed -i '' 's|\$(atuin uuid)|${_zsh_fast_session_id}|' "$cache" ;;
	zoxide) sed -i '' "s|\\\\command zoxide |\\\\command ${bin} |g" "$cache" ;;
	esac
}

# Source cached tool init. Stale caches: keep serving the old file, rewrite
# in the background for the next shell. Missing cache: generate in-process
# (callers run this after first prompt).
_zsh_eval_cached() {
	emulate -L zsh
	local name="$1"
	shift
	[[ $1 == -- ]] && shift
	(($#)) || return 1

	local cache="$_ZSH_INIT_CACHE/${name}.zsh"
	local -a gen=("$@")
	local binpath
	binpath="$(_zsh_binpath "${gen[1]}")" || return 1

	if [[ ! -s $cache ]]; then
		"${gen[@]}" >|"$cache" 2>/dev/null || return 1
		_zsh_init_cache_postprocess "$name" "$cache" "$binpath"
	elif [[ $binpath -nt $cache ]]; then
		(
			emulate -L zsh
			local tmp="${cache}.new.$$"
			"${gen[@]}" >|"$tmp" 2>/dev/null || {
				rm -f "$tmp"
				exit 1
			}
			_zsh_init_cache_postprocess "$name" "$tmp" "$binpath"
			mv -f "$tmp" "$cache"
		) &!
	fi
	[[ -s $cache ]] && source "$cache"
}
