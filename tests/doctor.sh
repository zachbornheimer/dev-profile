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
bash "$root/tests/hook-path-free.sh" >/dev/null || fail "hook path fixture"
bash "$root/tests/ban-trunk-prettier-fixture.sh" >/dev/null || fail "ban-trunk-prettier fixture"
bash "$root/tests/pre-push-empty-file-list-fixture.sh" >/dev/null || fail "pre-push empty file list fixture"
bash "$root/tests/semgrep-fixture.sh" >/dev/null || fail "semgrep fixture"
bash "$root/tests/dev-family-fixture.sh" "$root" >/dev/null || fail "dev-family fixture"
bash "$root/tests/commit-fix-fixture.sh" "$root" >/dev/null || fail "commit-fix fixture"
bash "$root/tests/skills-sync-fixture.sh" >/dev/null || fail "skills sync fixture"
for f in "$root"/bin/*; do
	bash -n "$f" || fail "bin/${f##*/}"
done
node --check "$root/dev-relay.mjs" || fail dev-relay.mjs
[ -f "$root/config/personal-overlay.toml" ] || fail config/personal-overlay.toml
echo "ok"
