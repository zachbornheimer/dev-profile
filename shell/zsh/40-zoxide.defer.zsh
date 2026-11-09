# 40-zoxide.defer.zsh — smarter cd.

[[ -x /opt/homebrew/bin/zoxide || -x $HOME/.local/bin/zoxide ]] &&
	_zsh_eval_cached zoxide -- zoxide init zsh --cmd cd

# `zoxide add` is bookkeeping, not part of cd: run it detached so the blocking
# cd path forks nothing for it (a fork here cost 0.1-1s when the machine is busy).
if ((${+functions[__zoxide_hook]})); then
	typeset -g _zoxide_bin="$(_zsh_binpath zoxide)"
	__zoxide_hook() {
		\command "$_zoxide_bin" add -- "$PWD" >/dev/null 2>&1 &!
	}
fi

# --cmd cd replaces `cd`; keep `z`/`zi` names the rest of the config expects.
(($+functions[z])) || function z { __zoxide_z "$@"; }
(($+functions[zi])) || function zi { __zoxide_zi "$@"; }
