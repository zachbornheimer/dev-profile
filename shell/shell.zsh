# The shell file a new interactive shell sources: mise activation (and the
# background cd hooks that go with it) from the mise.zsh beside this file,
# resolved through the ~/.local/share/dev-profile symlink, then worktrunk.
source "${${(%):-%x}:A:h}/mise.zsh"
command -v wt >/dev/null && eval "$(wt config shell init zsh)"
