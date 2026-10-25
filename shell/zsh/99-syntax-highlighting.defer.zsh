# 99-syntax-highlighting.defer.zsh — must load last: it wraps every widget bound so far.

if ((!$+functions[_zsh_highlight])) &&
	[[ -f /opt/homebrew/share/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh ]]; then
	source /opt/homebrew/share/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh
fi
