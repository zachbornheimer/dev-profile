#!/usr/bin/env bash
# Check the files this branch installs. There is no Pkl render.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
fail() {
	echo "FAIL: $*" >&2
	exit 1
}
HK_FILE="$root/hk/hk.pkl" hk validate >/dev/null || fail hk/hk.pkl
dprint output-resolved-config --config "$root/config/dprint.jsonc" >/dev/null || fail config/dprint.jsonc
zsh -n "$root/shell/shell.zsh" || fail shell/shell.zsh
for f in "$root"/shell/zsh/*.zsh; do
	zsh -n "$f" || fail "shell/zsh/${f##*/}"
done
bash "$root/tests/output-fixture.sh" >/dev/null || fail "output fixture"
for f in "$root"/bin/*; do
	bash -n "$f" || fail "bin/${f##*/}"
done
[ -f "$root/config/personal-overlay.toml" ] || fail config/personal-overlay.toml
echo "ok"
