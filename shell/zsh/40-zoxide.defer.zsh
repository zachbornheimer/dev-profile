# 40-zoxide.defer.zsh — smarter cd.

[[ -x /opt/homebrew/bin/zoxide || -x $HOME/.local/bin/zoxide ]] &&
	_zsh_eval_cached zoxide -- zoxide init zsh --cmd cd

# `zoxide add` is bookkeeping, not part of cd: run it detached through the
# normal PATH (the mise shim, ~0.5-0.9s) so cd never waits on it.
if ((${+functions[__zoxide_hook]})); then
	__zoxide_hook() {
		\command zoxide add -- "$PWD" >/dev/null 2>&1 &!
	}
fi

# --cmd cd replaces `cd`; keep `z`/`zi` names the rest of the config expects.
(($+functions[z])) || function z { __zoxide_z "$@"; }
(($+functions[zi])) || function zi { __zoxide_zi "$@"; }
