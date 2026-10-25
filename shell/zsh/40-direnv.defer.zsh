# 40-direnv.defer.zsh — direnv hook.

[[ -x /opt/homebrew/bin/direnv || -x $HOME/.local/bin/direnv ]] &&
	_zsh_eval_cached direnv -- direnv hook zsh
