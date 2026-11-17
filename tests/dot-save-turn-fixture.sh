#!/usr/bin/env bash
# Proves dev-profile-dot-save-turn records provenance and reports the real delta.
#
# Isolated HOME and mise state: nothing here touches the live dot history.
#   1. two tracked files dirty, one named -> exit 0, the checkpoint reports
#      trigger=agent, task=<ticket>, description_source=agent, the named path is
#      under `authored:` and the swept one under `captured-not-authored:`;
#   2. the swept path really is in the checkpoint (a snapshot, not a delta);
#   3. an untracked path exits non-zero and writes no checkpoint.
set -uo pipefail

repo=$(cd "$(dirname "$0")/.." && pwd)
save_turn="$repo/bin/dev-profile-dot-save-turn"
T=$(mktemp -d)
trap 'rm -rf "$T"' EXIT
export HOME="$T/home" MISE_CONFIG_DIR="$T/config/mise" MISE_STATE_DIR="$T/state" \
	MISE_DATA_DIR="$T/data" MISE_CACHE_DIR="$T/cache" MISE_QUIET=1
mkdir -p "$HOME" "$MISE_CONFIG_DIR" "$MISE_STATE_DIR"
printf '[dotfiles]\n' >"$MISE_CONFIG_DIR/config.toml"

fail() {
	printf 'FAIL: %s\n' "$1" >&2
	exit 1
}
latest_id() { mise dot history -J -n 1 2>/dev/null | jq -r '.[0].id'; }

printf 'a1\n' >"$HOME/.dot-a"
printf 'b1\n' >"$HOME/.dot-b"
mise dot track "$HOME/.dot-a" "$HOME/.dot-b" >/dev/null 2>&1 || fail "tracking the fixture"
mise dot save --description base >/dev/null 2>&1 || fail "baseline checkpoint"

printf 'a2-turn-wrote\n' >"$HOME/.dot-a"
printf 'b2-other-process-wrote\n' >"$HOME/.dot-b"

# 1 + 2. provenance and the split
out=$("$save_turn" ZYS-9739 "$HOME/.dot-a" 2>&1)
code=$?
[ "$code" -eq 0 ] || fail "a sweep must not fail the turn (exit $code): $out"
printf '%s' "$out" | grep -q 'trigger=agent' || fail "no agent trigger: $out"
printf '%s' "$out" | grep -q 'task=ZYS-9739' || fail "no task provenance: $out"
printf '%s' "$out" | grep -q 'description_source=agent' || fail "no agent description source: $out"

authored=$(printf '%s' "$out" | sed -n '/^authored:/,/^captured-not-authored:/p')
printf '%s' "$authored" | grep -q '~/.dot-a' || fail "the named path is not under authored: $out"
printf '%s' "$authored" | grep -q '~/.dot-b' && fail "the swept path is listed as authored: $out"
swept=$(printf '%s' "$out" | sed -n '/^captured-not-authored:/,$p')
printf '%s' "$swept" | grep -q '~/.dot-b' || fail "the swept path is not under captured-not-authored: $out"

# The checkpoint really holds both paths: this is a snapshot history, and the
# report is what keeps a turn's claim honest.
changed=$(mise dot history show latest --json 2>/dev/null | jq -r '.changes.modified | join(" ")')
[ "$changed" = "~/.dot-a ~/.dot-b" ] || fail "unexpected checkpoint change set: $changed"

# 3. an untracked path fails and creates nothing
before=$(latest_id)
printf 'x\n' >"$HOME/untracked.txt"
out=$("$save_turn" ZYS-9739 "$HOME/untracked.txt" 2>&1)
code=$?
[ "$code" -ne 0 ] || fail "an untracked path must fail: $out"
[ "$before" = "$(latest_id)" ] || fail "a refused save still wrote a checkpoint"

printf 'ok: agent provenance recorded, named path authored, swept path reported, untracked path refused\n'
