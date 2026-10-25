# 20-keybindings.zsh — line-editor bindings.

# Emacs line editing (Ctrl-A/E/K/U/W, Alt-B/F, Ctrl-Y, …). Without this, zsh
# picks VI keybindings because $EDITOR ("nvim") matches *vi*, which leaves
# Ctrl-A / Ctrl-E doing nothing (they fall back to self-insert).
bindkey -e
bindkey '\e[1;3D' backward-word
bindkey '\e[1;3C' forward-word
bindkey '\e[1;5D' backward-word
bindkey '\e[1;5C' forward-word
bindkey '^[[3~' delete-char
bindkey '^[[3;1~' delete-char
bindkey '^[[3u' delete-char
bindkey '^[[3;1u' delete-char
bindkey '^[[3;5~' kill-word
# Removing "/" makes Option+Arrows, Alt+Backspace and zsh-autosuggestions partial accept (forward-word) move one path segment at a time.
WORDCHARS=${WORDCHARS//\//}
