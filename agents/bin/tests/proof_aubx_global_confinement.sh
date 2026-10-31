#!/usr/bin/env bash
# proof_aubx_global_confinement.sh — prove one REAL guarded global install
# writes only inside ~/.agents/available-skills, then restore the roster
# exactly as found.
#
# The canary installs from a throwaway local source repo, so the proof never
# mutates a real skill and never depends on a third-party repo's state.
# Every durable write the installer makes is derived from $HOME; the guard
# (aubx) routes global skills verbs to aubx-skills, which runs the real
# installer under a throwaway HOME and copies the result into the roster.
#
# Exit 0 only when every assertion passes. Exit 3 = a write was observed
# outside the roster (mirrors aubx-skills' own tripwire). Exit 1 = anything
# else, including residue left after a failed remove.
set -uo pipefail

H="$HOME"
AUBX="$H/.agents/bin/aubx"
AVAIL="$H/.agents/available-skills"
RECORD="$AVAIL/.skill-lock.json"
CANARY="aubx-confinement-canary"

fail=0
good() { printf 'ok   - %s\n' "$*"; }
bad() {
	printf 'FAIL - %s\n' "$*" >&2
	fail=1
}

for f in "$AUBX" "$AVAIL" "$RECORD"; do
	[ -e "$f" ] || {
		printf 'FAIL - missing %s\n' "$f" >&2
		exit 1
	}
done
if [ -e "$AVAIL/$CANARY" ]; then
	printf 'FAIL - canary %s already in roster; remove it first\n' "$CANARY" >&2
	exit 1
fi

SCRATCH="$(mktemp -d /tmp/aubx-confinement-proof.XXXXXX)"
trap 'rm -rf "$SCRATCH"' EXIT

# One throwaway source repo with one uniquely named skill.
mkdir -p "$SCRATCH/repo/$CANARY"
cat >"$SCRATCH/repo/$CANARY/SKILL.md" <<'SKILL'
---
name: aubx-confinement-canary
description: Throwaway fixture for the aubx global-confinement proof. Never use for real work.
---

Proof fixture only; installed and removed by proof_aubx_global_confinement.sh.
SKILL

# Snapshot every path outside the roster the installer could reach: all of
# ~/.agents except available-skills, plus each harness skill root. fd, never
# find; each walk is timeout-bounded per the machine's search rules. A root
# that resolves inside the roster is skipped: writes there are allowed by
# definition, and spelling a path through a symlink is not evidence of a leak.
ROOTS=("$H/.agents" "$H/.claude/skills" "$H/.codex/skills" "$H/.grok/skills"
	"$H/.cursor/skills" "$H/.gemini/skills" "$H/.config/opencode/skills")
snap() {
	: >"$1"
	local d rd
	for d in "${ROOTS[@]}"; do
		[ -e "$d" ] || continue
		rd="$(cd -- "$d" 2>/dev/null && pwd -P)" || continue
		case "$rd" in
		"$AVAIL" | "$AVAIL"/*) continue ;;
		esac
		timeout 60 fd -HI -a . "$rd" >>"$1" 2>/dev/null || true
	done
	grep -v -e "^$AVAIL/" -e '\.DS_Store$' "$1" >"$1.f" || true
	sort -o "$1.f" "$1.f" && mv "$1.f" "$1"
}
roster_names() { (cd "$AVAIL" && printf '%s\n' *) | grep -v '^\.' | grep -v '^\*' | sort; }

snap "$SCRATCH/before"
roster_names >"$SCRATCH/roster-before"
record_keys_before="$(jq -r '.skills | keys[]' "$RECORD" 2>/dev/null | sort)"

# --- the real install, through the guard the user actually invokes ----------
"$AUBX" skills add "$SCRATCH/repo" --skill "$CANARY" -g -y \
	>"$SCRATCH/install.log" 2>&1
irc=$?
if [ "$irc" -eq 0 ]; then
	good "install exited 0"
else
	bad "install exited $irc"
	tail -5 "$SCRATCH/install.log" >&2
fi

snap "$SCRATCH/after-install"
leaks="$(comm -13 "$SCRATCH/before" "$SCRATCH/after-install")"
if [ -z "$leaks" ]; then
	good "no new path outside $AVAIL after install"
else
	printf 'FAIL - wrote outside %s:\n%s\n' "$AVAIL" "$leaks" >&2
	exit 3
fi

roster_names >"$SCRATCH/roster-installed"
new_in_roster="$(comm -13 "$SCRATCH/roster-before" "$SCRATCH/roster-installed")"
if [ "$new_in_roster" = "$CANARY" ]; then
	good "canary landed in the roster and nothing else changed"
else
	bad "roster changed unexpectedly: [$new_in_roster]"
fi
if jq -e --arg n "$CANARY" '.skills | has($n)' "$RECORD" >/dev/null 2>&1; then
	good "install record has the canary entry"
else
	bad "install record missing canary entry"
fi

# --- confined remove, still through the guard -------------------------------
"$AUBX" skills remove "$CANARY" -g -y >"$SCRATCH/remove.log" 2>&1
rrc=$?
if [ "$rrc" -eq 0 ]; then
	good "remove exited 0"
else
	bad "remove exited $rrc"
	tail -5 "$SCRATCH/remove.log" >&2
fi

snap "$SCRATCH/final"
added="$(comm -13 "$SCRATCH/before" "$SCRATCH/final")"
removed="$(comm -23 "$SCRATCH/before" "$SCRATCH/final")"
if [ -z "$added" ] && [ -z "$removed" ]; then
	good "no path outside $AVAIL added or removed by the whole run"
else
	printf 'FAIL - paths outside %s changed:\nadded:\n%s\nremoved:\n%s\n' \
		"$AVAIL" "$added" "$removed" >&2
	exit 3
fi

if [ -e "$AVAIL/$CANARY" ]; then
	bad "canary still in roster after remove"
	printf '       cleanup: %s skills remove %s -g -y\n' "$AUBX" "$CANARY" >&2
else
	good "canary removed from roster"
fi

roster_names >"$SCRATCH/roster-final"
if diff -q "$SCRATCH/roster-before" "$SCRATCH/roster-final" >/dev/null; then
	good "roster skill set exactly as found"
else
	bad "roster skill set changed:"
	diff "$SCRATCH/roster-before" "$SCRATCH/roster-final" >&2
fi

record_keys_after="$(jq -r '.skills | keys[]' "$RECORD" 2>/dev/null | sort)"
if printf '%s\n' "$record_keys_after" | grep -qx "$CANARY"; then
	bad "install record still has the canary entry"
elif [ "$record_keys_before" != "$record_keys_after" ]; then
	# Expected and healthy: the record gets pruned of entries whose source
	# path is gone (ghost entries from earlier throwaway-source installs).
	# The folder set is the authority on what the roster holds.
	printf 'note - record keys changed (ghost-entry prune or refresh):\n' >&2
	diff <(printf '%s\n' "$record_keys_before") \
		<(printf '%s\n' "$record_keys_after") >&2
else
	good "install record keys exactly as found"
fi

if [ "$fail" -eq 0 ]; then
	printf 'PASS - one real global aubx install wrote only inside %s\n' "$AVAIL"
	exit 0
fi
exit 1
