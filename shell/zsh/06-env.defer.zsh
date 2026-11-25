# How long one server validation of the service token stands. Every interactive shell used to spend an `op vault list`
# on the same unchanged token; the 1Password request allowance is shared with every Relay guest, canary and worker.
typeset -g _OP_TOKEN_VALIDATION_SECONDS=$((12 * 60 * 60))

# True when the 1Password server accepts `token`. One `op vault list` (a server round trip that 403s for a deleted
# service account; `op whoami` decodes the token locally and still passes) answers for the next
# _OP_TOKEN_VALIDATION_SECONDS: the stamp holds the token's SHA-256, never the token, so a changed token is asked about
# again at once and nothing secret is stored a second time. A refusal is never remembered.
_op_service_token_serves() {
	emulate -L zsh
	zmodload -F zsh/stat b:zstat
	zmodload zsh/datetime
	local token="$1" stamp="${XDG_STATE_HOME:-$HOME/.local/state}/dev-profile/op-service-token.validated"
	local digest="${$(print -rn -- "$token" | shasum -a 256)%% *}" validated
	local -a modified
	if [[ -n "$digest" && -r "$stamp" ]] && zstat -A modified +mtime -- "$stamp" 2>/dev/null &&
		((EPOCHSECONDS - modified[1] < _OP_TOKEN_VALIDATION_SECONDS)); then
		validated="$(<"$stamp")"
		[[ "$validated" == "$digest" ]] && return 0
	fi
	OP_SERVICE_ACCOUNT_TOKEN="$token" op vault list >/dev/null 2>&1 || return 1
	[[ -n "$digest" ]] && mkdir -p "${stamp:h}" && print -r -- "$digest" >|"$stamp"
	return 0
}
() {
	emulate -L zsh
	unsetopt xtrace verbose
	# zsh -lic is interactive too; only a real macOS terminal may recover via 1Password Desktop + Keychain.
	[[ $OSTYPE == darwin* && -o interactive && -t 0 && -t 1 ]] || return 0
	local service='org.zysys.op-service-account'
	local account="$USERNAME"
	local source='op://Personal/Agent Service Token'
	local token="${OP_SERVICE_ACCOUNT_TOKEN:-}"
	local cached_token="$token"

	(($+commands[op])) || return 0
	if [[ -z "$token" ]] || ! _op_service_token_serves "$token"; then
		# Recovery must use desktop authentication, not the suspect service token.
		if ! token=$(
			unset OP_SERVICE_ACCOUNT_TOKEN
			op read "$source/credential" 2>/dev/null
		) ||
			[[ -z "$token" ]]; then
			unset OP_SERVICE_ACCOUNT_TOKEN
			__ -t failed '1Password: unable to read Agent Service Token/credential; token not exported.'
			return 0
		fi
		if ! _op_service_token_serves "$token"; then
			unset OP_SERVICE_ACCOUNT_TOKEN
			__ -t failed '1Password: replacement service token failed op vault list; Keychain unchanged.'
			return 0
		fi
	fi
	export OP_SERVICE_ACCOUNT_TOKEN="$token"

	if [[ "$token" != "$cached_token" ]]; then
		if ! security add-generic-password -U -a "$account" -s "$service" \
			-l '1Password Service Account Token' -w "$token" >/dev/null 2>&1; then
			__ -t warn '1Password: token exported, but updating its Keychain entry failed.'
			return 0
		fi
		local stored_token
		if ! stored_token=$(security find-generic-password -a "$account" -s "$service" -w 2>/dev/null) ||
			[[ "$stored_token" != "$token" ]]; then
			__ -t warn '1Password: token exported, but Keychain read-back verification failed.'
		fi
	fi
}
