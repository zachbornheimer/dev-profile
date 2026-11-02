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
() {
	emulate -L zsh
	unsetopt xtrace verbose
	# Login commands never reach ZLE. Load the cached service token before .zshrc
	# sources the AI environment (which may run op inject). Desktop recovery stays
	# in 06-env.defer.zsh and requires a terminal.
	[[ -t 0 && -t 1 ]] || export OP_BIOMETRIC_UNLOCK_ENABLED=false
	# Keychain first (06-env.defer.zsh validates it against the server and heals
	# it after the first prompt), then the container's tmpfs seed. The Mac's
	# hand-staged secrets file is never read: a reset at my.1password.com
	# leaves it dead, and a dead token 403s every op call that carries it.
	if [[ -z ${OP_SERVICE_ACCOUNT_TOKEN:-} ]] && command -v security >/dev/null 2>&1; then
		local token
		if token=$(security find-generic-password -a "$USERNAME" \
			-s 'org.zysys.op-service-account' -w 2>/dev/null) && [[ -n "$token" ]]; then
			export OP_SERVICE_ACCOUNT_TOKEN="$token"
		elif [[ -r /run/secrets/op-service-account-token ]]; then
			export OP_SERVICE_ACCOUNT_TOKEN="$(</run/secrets/op-service-account-token)"
		fi
	fi
	return 0
}

export COREPACK_ENABLE_DOWNLOAD_PROMPT=0

# Shared Neon session store for omp across Mac front-end and remote compute arm.
if [[ -z ${SESSIONS_DB_URL:-} && -s $HOME/.config/dev-env/runtime/omp-session-db-url ]]; then
	export SESSIONS_DB_URL="$(<$HOME/.config/dev-env/runtime/omp-session-db-url)"
fi

ulimit -n 4096
export OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES
