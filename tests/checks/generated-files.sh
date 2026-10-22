#!/usr/bin/env bash
# Every generated file parses, and every script and hook step the profile names
# exists. Usage: generated-files.sh <generated-dir>
set -euo pipefail
. "$(dirname "$0")/common.sh"
out="${1:?usage: generated-files.sh <generated-dir>}"
grep -Fq "$out/bin/dev-profile-pkl-fmt" "$out/dprint.jsonc" || fail "dprint pkl exec must be $out/bin/dev-profile-pkl-fmt"
jq empty "$out/profile.json" || fail profile.json
luac -p "$out/conform.lua" || fail conform.lua
zsh -n "$out/shell.zsh" || fail shell.zsh
for f in "$out"/bin/*; do bash -n "$f" || fail "${f##*/}"; done
"$out/bin/dev-profile-git-config-hooks" || fail "git 2.54+ (config-based hooks) does not resolve"
# Every generated script runs under pipefail: a reader that stops early (head)
# kills its writer with SIGPIPE and the script with exit 141.
if grep -nE '[|][[:space:]]*head([[:space:]]|$)' "$out"/bin/*; then fail "a generated script pipes into head; under pipefail that exits 141. Use sed -n 1p or awk 'NR <= n'"; fi
grep -F "composer audit --locked" "$out/bin/dev-profile-contract-php" || fail "composer audit --locked"
while IFS= read -r cmd; do [[ -x "$out/bin/$cmd" ]] || fail "hk step command without a rendered bin script: $cmd"; done < <(grep -ohE "dev-profile-[a-z0-9-]+" "$out/src/profile.pkl" "$out"/src/tools/*/*.pkl | sort -u)
