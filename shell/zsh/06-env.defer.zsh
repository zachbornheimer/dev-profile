() {
	emulate -L zsh
	unsetopt xtrace verbose
	# zsh -lic is interactive too; only a real terminal may recover via desktop.
	[[ -o interactive && -t 0 && -t 1 ]] || return 0
	local service='org.zysys.op-service-account'
	local account="$USERNAME"
	local source='op://Personal/Agent Service Token'
	local token="${OP_SERVICE_ACCOUNT_TOKEN:-}" identity
	local cached_token="$token"

	(($+commands[op])) || return 0
	if [[ -z "$token" ]]; then
		token=$(
			unset OP_SERVICE_ACCOUNT_TOKEN
			op read "$source" 2>/dev/null
		) || token=''
	fi

	export OP_SERVICE_ACCOUNT_TOKEN="$token"
	if [[ -z "$token" ]] || ! identity=$(op whoami 2>&1) ||
		[[ "${(L)identity}" == *'account is not signed in'* ]]; then
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
		export OP_SERVICE_ACCOUNT_TOKEN="$token"
		if ! identity=$(op whoami 2>&1); then
			unset OP_SERVICE_ACCOUNT_TOKEN
			__ -t failed '1Password: replacement service token failed op whoami; Keychain unchanged.'
			return 0
		fi
	fi

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
