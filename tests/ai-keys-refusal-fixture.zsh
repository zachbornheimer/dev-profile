#!/usr/bin/env zsh
# A shell nobody is sitting at must not run `op inject` again for a token and template 1Password already refused:
# a Relay guest's identity can never resolve the template, and its agent starts a shell per command. Drives the real
# shell-start entry (apps/ai/env.sh, as home/zshrc sources it) in a scratch HOME against a recording `op`, and counts
# the `op` runs each shell start makes.
emulate -L zsh
setopt err_return no_unset pipe_fail
zmodload zsh/zpty zsh/zselect

root=${0:A:h:h}
work=$(mktemp -d "${TMPDIR:-/tmp}/ai-keys-refusal.XXXXXX")
trap 'zpty -d shell 2>/dev/null || true; rm -rf "$work"' EXIT
home="$work/home"
mkdir -p "$work/bin" "$home/.config/ai"
ln -s "$root/shell/zsh" "$home/.config/zsh"
print -r -- 'FIXTURE_API_KEY=op://Private/Fixture Key/credential' >"$home/.config/ai/keys.env.op"

# `op inject` succeeds only while $work/accepts exists; it then writes the file `-o` names.
cat >"$work/bin/op" <<'EOF'
#!/bin/sh
echo "$1" >>"$OP_FIXTURE/op.calls"
[ "$1" = inject ] && [ -e "$OP_FIXTURE/accepts" ] || exit 1
while [ $# -gt 1 ]; do
	[ "$1" = -o ] && out="$2"
	shift
done
printf 'export FIXTURE_API_KEY=resolved\n' >"$out"
EOF
chmod +x "$work/bin/op"

fail() {
	print -r -- "FAIL: $*" >&2
	exit 1
}

shell_env=(env HOME="$home" OP_FIXTURE="$work" PATH="$work/bin:$PATH" NO_COLOR=1)
calls() { [[ -s "$work/op.calls" ]] && print -r -- "$(<"$work/op.calls")" || true; }

# One interactive shell start with no terminal on stdin, as an agent's or a guest's shell has.
unattended_start() {
	: >"$work/op.calls"
	$shell_env OP_SERVICE_ACCOUNT_TOKEN="$1" zsh -fic "builtin source '$root/apps/ai/env.sh'" </dev/null >"$work/out" 2>&1 || true
}

# One interactive shell on a terminal running `command` with `token`: a person's shell start by default.
terminal_shell() {
	local command="${2:-builtin source '$root/apps/ai/env.sh'}" out="" chunk
	local -i idle=0
	: >"$work/op.calls"
	zpty -b shell $shell_env OP_SERVICE_ACCOUNT_TOKEN="$1" zsh -dfi
	zpty -w shell "$command; print -r -- \"STARTED<\$((1 + 1))>\""
	while [[ $out != *'STARTED<2>'* ]] && ((idle < 300)); do
		if zpty -r shell chunk; then
			out+="$chunk"
		else
			((++idle))
			zselect -t 10 || true
		fi
	done
	zpty -d shell
	[[ $out == *'STARTED<2>'* ]] || fail "the terminal shell did not finish: ${out[-300,-1]}"
}

refusal="$home/.cache/ai/keys.env.refused"

unattended_start guest-token
[[ "$(calls)" == inject ]] || fail "the first unattended shell did not ask once: $(calls)"
grep -q 'op inject failed' "$work/out" || fail "the first refusal was not reported: $(<"$work/out")"

unattended_start guest-token
[[ -z "$(calls)" ]] || fail "a second unattended shell start ran op again for a refused token: $(calls)"
grep -q "Run 'ai-keys-refresh' to retry now" "$work/out" || fail "the remembered refusal was not reported: $(<"$work/out")"
unattended_start guest-token
[[ -z "$(calls)" ]] || fail "a third unattended shell start ran op again for a refused token: $(calls)"
[[ -s $refusal ]] || fail "no refusal was recorded"
grep -rq guest-token "$home/.cache" && fail "the refusal record stores the token itself"

# The refusal is about one token and one template: another of either is asked about at once.
unattended_start other-token
[[ "$(calls)" == inject ]] || fail "a different token was covered by another token's refusal: $(calls)"
unattended_start other-token
print -r -- 'OTHER_API_KEY=op://Private/Other Key/credential' >>"$home/.config/ai/keys.env.op"
unattended_start other-token
[[ "$(calls)" == inject ]] || fail "a changed template was covered by the old template's refusal: $(calls)"

# An expired refusal is asked about again, and `ai-keys-refresh` retries at once.
unattended_start other-token
[[ -z "$(calls)" ]] || fail "the refusal did not stand for the changed template: $(calls)"
touch -t 202001010000 "$refusal"
unattended_start other-token
[[ "$(calls)" == inject ]] || fail "an expired refusal was trusted: $(calls)"
: >"$work/op.calls"
$shell_env OP_SERVICE_ACCOUNT_TOKEN=other-token zsh -fc "builtin source '$root/shell/zsh/ai-keys.zsh'; ai-keys-refresh" </dev/null >/dev/null 2>&1 || true
[[ "$(calls)" == inject ]] || fail "ai-keys-refresh did not retry a remembered refusal: $(calls)"

# A terminal alone does not make a shell attended: a guest's pty shell (not macOS) is covered by the refusal too.
[[ -s $refusal ]] || fail "the refresh's refusal was not recorded"
terminal_shell other-token "builtin source '$root/shell/zsh/ai-keys.zsh'; OSTYPE=linux-gnu; ai-keys::env"
[[ -z "$(calls)" ]] || fail "a guest's terminal shell ran op again for a refused token: $(calls)"

# A person at a Mac terminal can unlock 1Password, so their shells ask every time, refusal on record or not.
if [[ $OSTYPE == darwin* ]]; then
	terminal_shell other-token
	[[ "$(calls)" == inject ]] || fail "an attended shell did not ask while a refusal was on record: $(calls)"
	terminal_shell other-token
	[[ "$(calls)" == inject ]] || fail "a second attended shell did not ask again: $(calls)"
fi

# Once 1Password answers, the keys are cached, the refusal is gone, and later shells ask nothing.
: >"$work/accepts"
rm -f "$refusal"
unattended_start other-token
[[ "$(calls)" == inject ]] || fail "the accepted inject was not a single call: $(calls)"
[[ -s "$home/.cache/ai/keys.env" ]] || fail "an accepted inject left no cache"

# An accepted inject clears a refusal that was on record for it.
print -r -- 'THIRD_API_KEY=op://Private/Third Key/credential' >>"$home/.config/ai/keys.env.op"
rm -f "$work/accepts"
unattended_start other-token
[[ -s $refusal ]] || fail "the refusal for the newer template was not recorded"
: >"$work/accepts"
$shell_env OP_SERVICE_ACCOUNT_TOKEN=other-token zsh -fc "builtin source '$root/shell/zsh/ai-keys.zsh'; ai-keys-refresh" </dev/null >/dev/null 2>&1
[[ ! -e $refusal ]] || fail "an accepted inject left the refusal on record"
unattended_start other-token
[[ -z "$(calls)" ]] || fail "a shell start ran op with a current cache: $(calls)"

print -r -- "PASS: a shell that cannot change 1Password's answer asks once per refused token and template; a Mac terminal shell, a new token, a new template, an expired refusal and ai-keys-refresh ask again"
