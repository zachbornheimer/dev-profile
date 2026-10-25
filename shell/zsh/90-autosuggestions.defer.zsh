# 90-autosuggestions.defer.zsh — fish-style history suggestions.

ZSH_AUTOSUGGEST_USE_ASYNC=1
ZSH_AUTOSUGGEST_STRATEGY=(history completion)
ZSH_AUTOSUGGEST_HIGHLIGHT_STYLE='fg=#808080'
if ((!$+functions[_zsh_autosuggest_start])) &&
	[[ -f /opt/homebrew/share/zsh-autosuggestions/zsh-autosuggestions.zsh ]]; then
	source /opt/homebrew/share/zsh-autosuggestions/zsh-autosuggestions.zsh
fi
