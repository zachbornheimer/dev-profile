#!/usr/bin/env zsh
# A new interactive shell must not spend a 1Password request re-validating a service token the server already
# accepted: the allowance is shared with every Relay guest. Drives the real 06-env.defer.zsh in a pty against a
# recording `op` and `security`, and counts the calls each shell start makes.
emulate -L zsh
setopt err_return no_unset pipe_fail
zmodload zsh/zpty zsh/zselect

root=${0:A:h:h}
work=$(mktemp -d "${TMPDIR:-/tmp}/op-token-validation.XXXXXX")
trap 'zpty -d shell 2>/dev/null || true; rm -rf "$work"' EXIT
mkdir -p "$work/bin" "$work/state"

# `op vault list` succeeds only for the token named in $work/accepted; `op read` hands out that token.
cat >"$work/bin/op" <<'EOF'
#!/bin/sh
echo "$*" >>"$OP_FIXTURE/op.calls"
case "$1" in
vault) [ "${OP_SERVICE_ACCOUNT_TOKEN:-}" = "$(cat "$OP_FIXTURE/accepted")" ] ;;
read) cat "$OP_FIXTURE/accepted" ;;
*) exit 64 ;;
esac
EOF
cat >"$work/bin/security" <<'EOF'
#!/bin/sh
echo "$1" >>"$OP_FIXTURE/security.calls"
case "$1" in
add-generic-password) while [ $# -gt 1 ]; do shift; done; printf '%s' "$1" >"$OP_FIXTURE/keychain" ;;
find-generic-password) cat "$OP_FIXTURE/keychain" ;;
esac
EOF
chmod +x "$work/bin/op" "$work/bin/security"

fail() {
	print -r -- "FAIL: $*" >&2
	exit 1
}

# One interactive shell start with `token` in its environment; prints the token the shell ended up exporting.
start_shell() {
	local token="$1" out="" chunk
	: >"$work/op.calls"
	zpty -b shell env OP_FIXTURE="$work" XDG_STATE_HOME="$work/state" PATH="$work/bin:$PATH" \
		OP_SERVICE_ACCOUNT_TOKEN="$token" USERNAME=fixture zsh -dfi
	# The pty echoes this line back; the result pattern below matches lowercase token names only, never the echo.
	zpty -w shell "__() { print -r -- \"NOTE \$*\"; }; builtin source '$root/shell/zsh/06-env.defer.zsh'; print -r -- \"RESULT<\${OP_SERVICE_ACCOUNT_TOKEN:-none}>\""
	# Only an empty read counts against the wait: the pty hands the echo back a few bytes at a time.
	local -i idle=0
	while [[ ! $out =~ 'RESULT<[a-z-]+>' ]] && ((idle < 150)); do
		if zpty -r shell chunk; then
			out+="$chunk"
		else
			((++idle))
			zselect -t 10 || true
		fi
	done
	zpty -d shell
	[[ $out =~ 'RESULT<([a-z-]+)>' ]] || fail "the shell printed no result: ${out[-300,-1]}"
	REPLY=$match[1]
}
calls() { print -r -- "$(<"$work/op.calls")"; }

[[ $OSTYPE == darwin* ]] || {
	print -r -- "SKIP: the token recovery path is macOS-only"
	exit 0
}

print -rn -- good-token >"$work/accepted"

start_shell good-token
[[ $REPLY == good-token ]] || fail "a valid token was not kept (got $REPLY)"
[[ "$(calls)" == "vault list" ]] || fail "the first shell did not validate once: $(calls)"

start_shell good-token
[[ $REPLY == good-token ]] || fail "the second shell lost the token (got $REPLY)"
[[ -z "$(calls)" ]] || fail "a second shell start spent 1Password calls on an already validated token: $(calls)"

stamp="$work/state/dev-profile/op-service-token.validated"
[[ -s $stamp ]] || fail "no validation stamp was written"
grep -rq good-token "$work/state" && fail "the validation state stores the token itself"
# A different token is never covered by another token's stamp.
start_shell other-token
[[ $REPLY == good-token ]] || fail "a refused token was not replaced through desktop recovery (got $REPLY)"
[[ "$(calls)" == $'vault list\nread op://Personal/Agent Service Token/credential' ]] ||
	fail "a refused token did not cost exactly one validation and one recovery read: $(calls)"
[[ "$(<"$work/keychain")" == good-token ]] || fail "the recovered token did not reach the Keychain"

# An expired stamp is asked about again; a refusal is never remembered.
touch -t 202001010000 "$stamp"
start_shell good-token
[[ "$(calls)" == "vault list" ]] || fail "an expired stamp was trusted: $(calls)"
print -rn -- rotated-token >"$work/accepted"
rm -f "$stamp"
start_shell stale-token
start_shell stale-token
[[ "$(calls)" == *"vault list"* ]] || fail "a refused token's refusal was remembered: $(calls)"

print -r -- "PASS: a validated service token costs no 1Password call on later shell starts; a changed, expired or refused token is asked about again"
