# Keep kitty tab titles and the macOS menu bar showing the current path.
autoload -Uz add-zsh-hook
_title_precmd() { printf '\033]0;%s\007' "${PWD/#$HOME/~}"; }
add-zsh-hook precmd _title_precmd
