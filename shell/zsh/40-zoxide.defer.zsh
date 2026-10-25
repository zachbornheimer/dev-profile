# 40-zoxide.defer.zsh — smarter cd.

[[ -x /opt/homebrew/bin/zoxide || -x $HOME/.local/bin/zoxide ]] &&
	_zsh_eval_cached zoxide -- zoxide init zsh --cmd cd

# --cmd cd replaces `cd`; keep `z`/`zi` names the rest of the config expects.
(($+functions[z])) || function z { __zoxide_z "$@"; }
(($+functions[zi])) || function zi { __zoxide_zi "$@"; }
