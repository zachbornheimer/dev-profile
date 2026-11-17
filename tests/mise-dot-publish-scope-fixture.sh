#!/usr/bin/env bash
# Proves dev-profile-dot-publish publishes only the paths a turn named.
#
# Isolated HOME and mise state: nothing here touches the live dot history.
#   1. another tracked path is dirty and unnamed -> the save is refused, exit 2,
#      and its name and reason are printed;
#   2. --allow-extras proceeds but still names the extra as untouched;
#   3. a save with only the authored path dirty publishes exactly that path.
set -uo pipefail

repo=$(cd "$(dirname "$0")/.." && pwd)
publish="$repo/bin/dev-profile-dot-publish"
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

printf 'a\n' >"$HOME/a.txt"
printf 'b\n' >"$HOME/b.txt"
mise dot track "$HOME/a.txt" "$HOME/b.txt" >/dev/null 2>&1 || fail "tracking the fixture"
mise dot save --description base >/dev/null 2>&1 || fail "baseline checkpoint"

names_of() {
	mise dot history -J -n 1 -n 1 2>/dev/null | jq -r '.[0].changes.modified // [] | join(" ")'
}

# 1. unnamed dirty path -> refusal, nothing saved
printf 'turn-a\n' >"$HOME/a.txt"
printf 'other-process\n' >"$HOME/b.txt"
before=$(mise dot history -J -n 1 2>/dev/null | jq -r '.[0].id')
out=$("$publish" --description "turn work" --paths "$HOME/a.txt" 2>&1)
code=$?
[ "$code" -eq 2 ] || fail "expected exit 2 on an unnamed dirty path, got $code: $out"
printf '%s' "$out" | grep -q '~/b.txt' || fail "the refusal did not name the extra path: $out"
printf '%s' "$out" | grep -q 'modified outside this turn' || fail "the extra had no reason: $out"
after=$(mise dot history -J -n 1 2>/dev/null | jq -r '.[0].id')
[ "$before" = "$after" ] || fail "the refused save still wrote a checkpoint ($before -> $after)"

# 2. --allow-extras publishes, and still reports the extra as untouched
out=$("$publish" --description "turn work" --paths "$HOME/a.txt" --allow-extras 2>&1)
code=$?
[ "$code" -eq 0 ] || fail "--allow-extras did not proceed (exit $code): $out"
printf '%s' "$out" | grep -q 'untouched  ~/b.txt' || fail "the accepted extra was not reported: $out"

# 3. only the authored path dirty -> the checkpoint names exactly that path
printf 'quiet\n' >"$HOME/b.txt"
mise dot save --description "quiet b" >/dev/null 2>&1 || fail "checkpointing the clean-up"
printf 'turn-a2\n' >"$HOME/a.txt"
out=$("$publish" --description "turn work 2" --paths "$HOME/a.txt" 2>&1)
code=$?
[ "$code" -eq 0 ] || fail "a clean save failed (exit $code): $out"
names=$(names_of)
[ "$names" = "~/a.txt" ] || fail "checkpoint named '$names', expected only '~/a.txt'"

printf 'ok: refused extras, reported accepted extras, and saved only the authored path\n'
