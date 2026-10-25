# 60-cli-aliases.defer.zsh — modern-CLI aliases. Interactive-only: they shadow POSIX commands.

if [[ -x /opt/homebrew/bin/eza ]]; then
	alias ls='eza --hyperlink=auto'
	alias ll='eza -lah --git --hyperlink=auto'
	alias la='eza -la --hyperlink=auto'
fi
[[ -x /opt/homebrew/bin/bat ]] && alias cat='bat'
[[ -x /opt/homebrew/bin/dust ]] && alias du='dust'
[[ -x /opt/homebrew/bin/duf ]] && alias df='duf'
[[ -x /opt/homebrew/bin/btop ]] && alias htop='btop'
[[ -x /opt/homebrew/bin/rg ]] && alias grep='rg --hyperlink-format=kitty'
[[ -x /opt/homebrew/bin/kitten ]] && alias icat='kitten icat'
[[ -x /opt/homebrew/bin/lazygit ]] && alias lg='lazygit'
