# 00-path.zsh — PATH, FPATH and Homebrew static env; every later module assumes these.

# 1Password SSH agent. Some SSH/Git clients read ~/.ssh/config's IdentityAgent,
# but tools like ssh-add and many GUI clients only honor SSH_AUTH_SOCK.
[[ -S "$HOME/Library/Group Containers/2BUA8C4S2C.com.1password/t/agent.sock" ]] && export SSH_AUTH_SOCK="$HOME/Library/Group Containers/2BUA8C4S2C.com.1password/t/agent.sock"

# Deduplicate PATH and other path-like variables.
# -g: this file is sourced from inside a function, where a bare typeset is local.
typeset -gU path PATH fpath FPATH

# Base Paths — mise shims give instant node/go/etc without `mise activate`
# (no per-prompt hook-env). uv shims stay first.
path=(
	"$HOME/.agents/bin"
	"$HOME/.opencode/bin"
	"$HOME/.local/bin"
	"$HOME/.local/share/dev-profile/bin"
	"$HOME/.local/share/mise/shims"
	"$HOME/.bun/bin"
	"$HOME/.local/share/aube/bin"
	"$HOME/Library/pnpm"
	"$HOME/Library/pnpm/bin"
	"$HOME/.cargo/bin"
	"$HOME/go/bin"
	"$HOME/.composer/vendor/bin"
	/opt/homebrew/bin
	/opt/homebrew/sbin
	/usr/local/bin
	/usr/local/sbin
	/usr/bin
	/bin
	/usr/sbin
	/sbin
	/Applications/kitty.app/Contents/MacOS
)
# Perl local::lib bin (Homebrew Perl only) sits right after ~/.agents/bin.
[[ -x /opt/homebrew/bin/perl ]] && path[2,3]=("$HOME/.local/bin" "$HOME/perl5/bin")
export PATH

# Homebrew — static env (skip `brew shellenv` + path_helper).
export HOMEBREW_PREFIX="/opt/homebrew"
export HOMEBREW_CELLAR="/opt/homebrew/Cellar"
export HOMEBREW_REPOSITORY="/opt/homebrew"
fpath=("/opt/homebrew/share/zsh/site-functions" $fpath)
export FPATH
export INFOPATH="/opt/homebrew/share/info${INFOPATH:+:$INFOPATH}"

# Completions (compinit) run after the first prompt — see 20-completion.defer.zsh.
fpath=(${fpath:#/usr/local/share/zsh/site-functions})
