# 10-history.defer.zsh — history settings. share_history must outlive the loader, so no emulate -L.

HISTFILE="$HOME/.zsh_history"
HISTSIZE=50000
SAVEHIST=50000
setopt append_history share_history hist_ignore_all_dups hist_reduce_blanks hist_verify
