# AI Tools
# Secrets for the supported AI tools (omp, Codex desktop) are resolved once
# via `op inject` into a private cache, not on every launch via `op run` —
# avoids a 1Password round-trip per invocation. `ai-keys-refresh` forces a
# re-inject when the template changes.
# env.sh resolves keys with `zsh -fc`, which never loads the module that
# defines `__`. Load it here so every failure still goes through `__`.
if ((!$+functions[__])); then
	builtin source "${ZSH_CONFIG_DIR:-$HOME/.config/zsh}/01-output.zsh"
fi

ai-keys::env() {
	local template="$HOME/.config/ai/keys.env.op"
	local cache_dir="$HOME/.cache/ai"
	local cache="$cache_dir/keys.env"

	if [[ ! -f "$template" ]]; then
		__ -t failed "ai-keys::env: missing template $template"
		return 1
	fi

	if [[ -f "$cache" && "$cache" -nt "$template" ]]; then
		print -r -- "$cache"
		return 0
	fi

	(umask 077 && mkdir -p "$cache_dir") || {
		__ -t failed "ai-keys::env: failed to create $cache_dir"
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
		__ -t failed "ai-keys::env: mktemp failed in $cache_dir"
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

	# The service token comes from the ambient env (05-env.zsh loaded it from
	# the Keychain; 06-env.defer.zsh validates and heals it). The hand-staged
	# secrets file is never read — a reset at my.1password.com leaves it dead.
	local op_token="${OP_SERVICE_ACCOUNT_TOKEN:-}"
	if ! (umask 077 && OP_SERVICE_ACCOUNT_TOKEN="$op_token" op inject -f -i "$mustache_tmpl" -o "$tmp") >/dev/null 2>&1; then
		rm -f "$tmp" "$mustache_tmpl"
		__ -t failed "ai-keys::env: op inject failed; run 'ai-keys-refresh' after checking 1Password sign-in"
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
		__ -t failed "ai-keys::exec: $name not found in PATH"
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

codex() { ai-keys::exec codex "$@"; }
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
