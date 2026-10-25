# 40-worktrunk.defer.zsh — worktrunk shell integration.

if ((${+commands[wt]})); then
	_zsh_eval_cached wt -- wt config shell init zsh
fi
