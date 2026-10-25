# 30-fzf.defer.zsh — fzf completion and key bindings. Must load before atuin (both bind ^R).

if [[ -f /opt/homebrew/opt/fzf/shell/completion.zsh ]]; then
	source /opt/homebrew/opt/fzf/shell/completion.zsh
	source /opt/homebrew/opt/fzf/shell/key-bindings.zsh
elif [[ -x /opt/homebrew/bin/fzf ]]; then
	_zsh_eval_cached fzf -- fzf --zsh
fi

if [[ -x /opt/homebrew/bin/fd ]]; then
	export FZF_DEFAULT_COMMAND='fd --type f --hidden --exclude .git'
	export FZF_CTRL_T_COMMAND="$FZF_DEFAULT_COMMAND"
fi
