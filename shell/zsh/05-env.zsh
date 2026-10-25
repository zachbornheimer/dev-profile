# 05-env.zsh — exported environment variables.

# Go
export GOPATH="$HOME/go"

# Perl (Standardized on Homebrew + isolated local::lib)
if [[ -x /opt/homebrew/bin/perl ]]; then
	# Initialize local::lib for the Homebrew Perl
	export PERL_LOCAL_LIB_ROOT="$HOME/perl5"
	export PERL_MB_OPT="--install_base \"$HOME/perl5\""
	export PERL_MM_OPT="INSTALL_BASE=$HOME/perl5"
	export PERL5LIB="$HOME/perl5/lib/perl5${PERL5LIB+:}${PERL5LIB}"
fi

# pnpm (its bin dirs are on PATH via 00-path.zsh)
export PNPM_HOME="${PNPM_HOME:-$HOME/Library/pnpm}"

export EDITOR='nvim'
export VISUAL='nvim'

export FZF_DEFAULT_OPTS='--height 40% --layout=reverse --border'

# bat: ripgrep config path and man page rendering.
export RIPGREP_CONFIG_PATH="$HOME/.config/ripgrep/config"
export MANPAGER="sh -c 'col -bx | bat -l man -p'"

# GUI sudo: when sudo runs without a controlling TTY (scripts launched from an
# editor/agent), `sudo -A` pops a native macOS password dialog via this helper.
export SUDO_ASKPASS="$HOME/Developer/Personal/dotfiles/bin/sudo-askpass"

# 1Password SSH key mirror used by opssh.zsh (refresh with `op-ssh-sync`).
export OP_SSH_DIR="$HOME/.ssh/1p"

export COREPACK_ENABLE_DOWNLOAD_PROMPT=0

ulimit -n 4096
export OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES
