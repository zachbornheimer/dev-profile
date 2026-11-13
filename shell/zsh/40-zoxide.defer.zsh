# 40-zoxide.defer.zsh — smarter cd.

[[ -x /opt/homebrew/bin/zoxide || -x $HOME/.local/bin/zoxide ]] &&
	_zsh_eval_cached zoxide -- zoxide init zsh --cmd cd

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

# Upstream probes an ordinary path with `(builtin cd -q ...)` before doing the
# real cd. Even that subshell costs tens to hundreds of ms under load. File
# tests cover explicit paths and CDPATH without a fork; fuzzy jumps stay upstream.
if ((${+functions[__zoxide_z]})); then
	cd() {
		if (($# == 1)); then
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
		__zoxide_z "$@"
	}
fi

# --cmd cd replaces `cd`; keep `z`/`zi` names the rest of the config expects.
(($+functions[z])) || function z { __zoxide_z "$@"; }
(($+functions[zi])) || function zi { __zoxide_zi "$@"; }
