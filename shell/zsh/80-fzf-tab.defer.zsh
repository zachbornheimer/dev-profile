# 80-fzf-tab.defer.zsh — fzf-powered tab completion. After compinit; before autosuggestions.

if [[ -f /opt/homebrew/share/fzf-tab/fzf-tab.zsh ]]; then
	zstyle ':completion:*:descriptions' format '[%d]'
	zstyle ':fzf-tab:*' use-fzf-default-opts yes
	zstyle ':fzf-tab:complete:cd:*' fzf-preview 'eza --tree --color=always --level=2 --icons $realpath 2>/dev/null | head -200'
	zstyle ':fzf-tab:complete:(kill|ps):*' fzf-preview 'ps -p $word -o comm= 2>/dev/null'
	(($+functions[enable-fzf-tab])) || source /opt/homebrew/share/fzf-tab/fzf-tab.zsh
fi
