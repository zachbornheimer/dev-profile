# 40-zoxide.defer.zsh — smarter cd.

typeset -g _zoxide_bin
_zoxide_bin="$(_zsh_binpath zoxide)" || return 0
_zsh_eval_cached zoxide -- "$_zoxide_bin" init zsh --cmd cd

# `zoxide add` is bookkeeping, not part of cd: it forks (a fork of this shell is
# ~1ms idle and 30ms+ when busy) and execs the mise shim (~0.5-0.9s). Both wait
# until the prompt is up (_p_after_prompt_defer, 30-prompt.zsh), and the exec
# is detached.
typeset -ga _zoxide_pending=()
_zoxide_add_pending() {
	local d
	for d in "${_zoxide_pending[@]}"; do
		\command zoxide add -- "$d" >/dev/null 2>&1 &!
	done
	_zoxide_pending=()
}
if ((${+functions[__zoxide_hook]})); then
	__zoxide_hook() {
		_zoxide_pending+=("$PWD")
		_p_after_prompt_defer _zoxide_add_pending
	}
fi

# Target lookup must finish before cd can change this shell's PWD. Resolve it
# with the native binary, never the mise shim; PATH and detached adds stay intact.
# Ordinary paths and directory-stack jumps need no query or probe subshell.
if ((${+functions[__zoxide_z]})); then
	__zoxide_z() {
		__zoxide_doctor
		if (($# == 0)); then
			__zoxide_cd ~
			return $?
		elif (($# == 1)) && [[ $1 == - ]]; then
			__zoxide_cd "$OLDPWD"
			return $?
		elif (($# == 1)) && [[ $1 == [-+]<-> ]]; then
			__zoxide_cd "$1"
			return $?
		elif (($# == 2)) && [[ $1 == -- ]]; then
			__zoxide_cd "$2"
			return $?
		elif (($# == 1)); then
			local base
			if [[ -d $1 ]]; then
				__zoxide_cd "$1"
				return $?
			fi
			if [[ $1 != /* ]]; then
				for base in "${cdpath[@]}"; do
					if [[ -d $base/$1 ]]; then
						__zoxide_cd "$1"
						return $?
					fi
				done
			fi
		fi
		local result
		result="$("$_zoxide_bin" query --exclude "$(__zoxide_pwd)" -- "$@")" && __zoxide_cd "$result"
	}
	cd() { __zoxide_z "$@"; }
	z() { __zoxide_z "$@"; }
	(($+functions[zi])) || function zi { __zoxide_zi "$@"; }
fi
