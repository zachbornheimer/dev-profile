#!/usr/bin/env bash
# Check the files this branch installs. There is no Pkl render.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
# Every check runs even after one fails: a fixture that dies silently cost three
# CI round trips, and an abort-on-first-failure suite reports one per run.
failed=()
fail() {
	echo "FAIL: $*" >&2
	failed+=("$*")
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
bash "$root/tests/dprint-ts-js-fixture.sh" >/dev/null || fail "dprint-ts-js fixture"
bash "$root/tests/retire-legacy-hooks-fixture.sh" "$root" >/dev/null || fail "retire-legacy-hooks fixture"
bash "$root/tests/pre-push-empty-file-list-fixture.sh" >/dev/null || fail "pre-push empty file list fixture"
bash "$root/tests/pre-push-refs-fixture.sh" >/dev/null || fail "pre-push refs fixture"
bash "$root/tests/ruby-security-steps-fixture.sh" >/dev/null || fail "ruby security steps fixture"
bash "$root/tests/brakeman-fixture.sh" >/dev/null || fail "brakeman introduced-only fixture"
bash "$root/tests/pre-commit-fixture.sh" >/dev/null || fail "pre-commit fixture"
bash "$root/tests/dev-family-fixture.sh" "$root" >/dev/null || fail "dev-family fixture"
bash "$root/tests/commit-fix-fixture.sh" "$root" >/dev/null || fail "commit-fix fixture"
bash "$root/tests/done-fixture.sh" "$root" >/dev/null || fail "done fixture"
bash "$root/tests/skills-sync-fixture.sh" >/dev/null || fail "skills sync fixture"
bash "$root/tests/unowned-repo-conventions-fixture.sh" >/dev/null || fail "unowned-repo-conventions fixture"
bash "$root/tests/worktree-copy-excludes-fixture.sh" "$root" >/dev/null || fail "worktree copy excludes fixture"
bash "$root/tests/changed-files-fixture.sh" >/dev/null || fail "changed-files fixture"
bash "$root/tests/pre-push-upstream-merge.sh" >/dev/null || fail "pre-push upstream merge fixture"
bash "$root/tests/mise-dot-encryption-heal-fixture.sh" >/dev/null || fail "mise dot encryption heal fixture"
bash "$root/tests/php-fmt-basepath-fixture.sh" >/dev/null || fail "php fmt basepath fixture"
bash "$root/tests/mise-history-watchdog-repair-fixture.sh" >/dev/null || fail "mise history watchdog repair fixture"
bash "$root/tests/probe-build-fixture.sh" >/dev/null || fail "probe-build fixture"
bash "$root/tests/uv-lock-cooldown-fixture.sh" "$root" >/dev/null || fail "uv-lock-cooldown fixture"
bash "$root/tests/tools-install-fixture.sh" "$root" >/dev/null || fail "tools install fixture"
for f in "$root"/bin/*; do
	# A directory that a previous run left behind (a stray __pycache__, say) is not
	# an installed entrypoint, and `head -1` on it fails the check for a file that
	# is not there: the worktree copy carries one into every fresh worktree.
	[ -f "$f" ] || continue
	if head -1 "$f" | grep -q python; then
		python3 -c 'import ast, sys; ast.parse(open(sys.argv[1]).read(), sys.argv[1])' "$f" ||
			fail "bin/${f##*/}"
	else
		bash -n "$f" || fail "bin/${f##*/}"
	fi
done
node --check "$root/dev-relay.mjs" || fail dev-relay.mjs
[ -f "$root/config/personal-overlay.toml" ] || fail config/personal-overlay.toml
if [ "${#failed[@]}" -gt 0 ]; then
	echo "FAIL: ${#failed[@]} check(s) failed" >&2
	exit 1
fi
echo "ok"
