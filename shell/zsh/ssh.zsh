# Durable SSH wrappers — source after any kitty/kiro init that defines `ssh`.
# Synology/BusyBox remotes break `kitten ssh` shell-integration ("environment:
# line 18: /dev/stderr: Permission denied"). Skip kitten for those hosts.
# tmux cannot complete the kitten's TTY bootstrap exchange, so use OpenSSH there.

# Hosts / substrings that must use plain OpenSSH (not kitten ssh).
typeset -ga ZSH_SSH_PLAIN_HOST_PATTERNS
ZSH_SSH_PLAIN_HOST_PATTERNS=(
	'192.168.1.99'
	'gorillabank'
	'ravn@'
	'wpengine.net'
	'synology'
	# kitten TTY bootstrap leaves empty untar dir → missing bootstrap-utils.sh
	'zysys'
	'zysyshosting.com'
)

ssh::use-plain() {
	local arg p
	for arg in "$@"; do
		for p in "${ZSH_SSH_PLAIN_HOST_PATTERNS[@]}"; do
			[[ "$arg" == *"$p"* ]] && return 0
		done
	done
	return 1
}

ssh() {
	if [[ -n ${KITTY_WINDOW_ID:-} ]] &&
		[[ -z ${TMUX:-} ]] &&
		(($+commands[kitten])) &&
		! ssh::use-plain "$@"; then
		kitten ssh "$@"
	else
		command ssh "$@"
	fi
}

# Short durable helper for the NAS (always plain OpenSSH).
ssh-nas() {
	command ssh ravn@192.168.1.99 "$@"
}

# Host alias style: `ssh nas` works if ~/.ssh/config has Host nas
# (we also define a convenience function for scripts).
nas() {
	command ssh ravn@192.168.1.99 "$@"
}
