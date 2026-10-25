# 35-atuin.defer.zsh — atuin history search. Loads after fzf: both bind ^R.

if [[ -x /opt/homebrew/bin/atuin || -x $HOME/.local/bin/atuin ]]; then
	export ATUIN_NOBIND=true
	_zsh_eval_cached atuin -- atuin init zsh
	bindkey '^r' atuin-search
	bindkey -M vicmd '^r' atuin-search
	(($+functions[atuin-search])) || function atuin-search { _atuin_search "$@"; }
fi
