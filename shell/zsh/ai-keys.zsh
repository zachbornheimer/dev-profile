# AI Tools
# claude CLI is commander-style: `claude <subcommand> [options]`. Global flags
# placed before a subcommand get consumed by the top-level parser and the
# subcommand name falls through as the [prompt] positional instead of routing
# to the subcommand (e.g. `claude --remote-control agents` errors with
# "Input must be provided either through stdin or as a prompt argument when
# using --print"). So: known subcommands run bare; everything else (plain
# prompt, --resume/-r/-c, interactive session) keeps the skip-permissions +
# remote-control defaults.
# Secrets for every AI CLI (claude, codex, opencode, grok) are resolved once
# via `op inject` into a private cache, not on every launch via `op run` —
# avoids a 1Password round-trip per invocation. `ai-keys-refresh` forces a
# re-inject when the template changes.
# `__` lives in 01-output.zsh, which a non-interactive shell never loads: env.sh
# resolves keys with `zsh -fc`, and that shell has no `__`. Report through `__`
# when it is there and fall back to plain stderr otherwise, so a stale cache can
# still say what went wrong instead of dying on `command not found: __`.
ai-keys::fail() {
	if (($+functions[__])); then
		__ -t failed "$1"
	else
		print -ru2 -- "✘ $1"
	fi
	return 1
}

ai-keys::env() {
	local template="$HOME/.config/ai/keys.env.op"
	local cache_dir="$HOME/.cache/ai"
	local cache="$cache_dir/keys.env"

	if [[ ! -f "$template" ]]; then
		ai-keys::fail "ai-keys::env: missing template $template"
		return 1
	fi

	if [[ -f "$cache" && "$cache" -nt "$template" ]]; then
		print -r -- "$cache"
		return 0
	fi

	(umask 077 && mkdir -p "$cache_dir") || {
		ai-keys::fail "ai-keys::env: failed to create $cache_dir"
		return 1
	}

	# op inject scans the whole file for bare `op://` text (no {{ }}
	# required), so the template's own comment lines (which mention
	# `op://` in prose) parse as broken references. Strip comments/blank
	# lines and wrap each real ref in {{ }} before injecting. Each line is
	# written as `export NAME=...` so a plain `source` of the cache exports
	# the keys to child processes, not only ai-keys::exec.
	local mustache_tmpl
	mustache_tmpl="$(mktemp "$cache_dir/keys.env.tmpl.XXXXXX")" || {
		ai-keys::fail "ai-keys::env: mktemp failed in $cache_dir"
		return 1
	}
	chmod 600 "$mustache_tmpl"
	command grep -E '^[A-Z_][A-Z0-9_]*=op://' "$template" |
		sed -E 's#^([A-Z_][A-Z0-9_]*)=(op://.*)$#export \1={{ \2 }}#' \
			>"$mustache_tmpl"

	# mktemp -u only reserves a name; op inject refuses to overwrite an
	# already-existing file without --force, so the output path must not
	# exist yet when op inject creates it.
	local tmp
	tmp="$(mktemp -u "$cache_dir/keys.env.XXXXXX")"

	if ! (umask 077 && op inject -f -i "$mustache_tmpl" -o "$tmp") >/dev/null 2>&1; then
		rm -f "$tmp" "$mustache_tmpl"
		ai-keys::fail "ai-keys::env: op inject failed; run 'ai-keys-refresh' after checking 1Password sign-in"
		return 1
	fi
	chmod 600 "$tmp"
	rm -f "$mustache_tmpl"

	mv -f "$tmp" "$cache"
	print -r -- "$cache"
}

ai-keys-refresh() {
	rm -f "$HOME/.cache/ai/keys.env"
	ai-keys::env >/dev/null
}

# Run a binary with the resolved keys exported. `whence -p` skips the shell
# wrapper of the same name so `codex() { ai-keys::exec codex "$@" }` is safe.
ai-keys::exec() {
	local name="$1"
	shift
	local bin keys_env
	bin="$(whence -p "$name")" || {
		ai-keys::fail "ai-keys::exec: $name not found in PATH"
		return 127
	}
	keys_env="$(ai-keys::env)" || return 1
	(
		set -a
		source "$keys_env"
		set +a
		exec "$bin" "$@"
	)
}

claude::bin() {
	local known_subcommands=(
		agents attach auth auto-mode doctor gateway import install logs mcp
		plugin plugins project respawn rm setup-token stop kill ultrareview
		update upgrade
	)
	local -a claude_args
	if (($# > 0)) && ((${known_subcommands[(Ie)$1]})); then
		claude_args=("$@")
	else
		claude_args=(--allow-dangerously-skip-permissions --dangerously-skip-permissions --remote-control --chrome "$@")
	fi
	ai-keys::exec claude "${claude_args[@]}"
}
claude() { claude::bin "$@"; }
c() { claude::bin "$@"; }
codex() { ai-keys::exec codex "$@"; }
opencode() { ai-keys::exec opencode "$@"; }

# WORK PROFILE — separate config dir (its own settings.json → work Linear MCP) +
# work-vault keys. Scaffold ~/.claude-work first, then uncomment:
# alias claude-work='CLAUDE_CONFIG_DIR="$HOME/.claude-work" op run --no-masking --env-file="$HOME/.config/claude/keys.work.env.op" -- claude'

# GitHub MCP — do not fork `gh auth token` on every shell start.
# When a tool needs it: `_zsh_github_token_ensure` (or export yourself).
_zsh_github_token_ensure() {
	emulate -L zsh
	[[ -n ${GITHUB_PERSONAL_ACCESS_TOKEN:-} ]] && return 0
	local tok
	tok="$(command gh auth token 2>/dev/null)" || return 1
	[[ -n $tok ]] || return 1
	export GITHUB_PERSONAL_ACCESS_TOKEN="$tok"
}
