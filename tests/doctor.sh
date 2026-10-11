#!/usr/bin/env bash
# `mise run doctor`: syntax-check every generated file with the tool that consumes it.
set -euo pipefail
out="$DEV_PROFILE_OUT"
fail() {
	echo "FAIL: $*" >&2
	exit 1
}
HK_FILE="$out/hk-config.pkl" hk validate >/dev/null || fail hk-config.pkl
dprint output-resolved-config --config "$out/dprint.jsonc" >/dev/null || fail dprint.jsonc
wt --config "$out/worktrunk.toml" config show >/dev/null || fail worktrunk.toml
for alias in up pr pr-draft pr-auto ship ship-all prune sync reconcile tidy retire; do
	wt --config "$out/worktrunk.toml" config alias show "$alias" >/dev/null || fail "worktrunk alias $alias"
done
wt --config "$out/worktrunk.toml" config alias dry-run pr -- @ >/dev/null || fail worktrunk alias dry-run pr
grep -Fq "$out/bin/dev-profile-pkl-fmt" "$out/dprint.jsonc" || fail "dprint pkl exec must be $out/bin/dev-profile-pkl-fmt"
jq empty "$out/profile.json" || fail profile.json
luac -p "$out/conform.lua" || fail conform.lua
zsh -n "$out/shell.zsh" || fail shell.zsh
for f in "$out"/bin/*; do bash -n "$f" || fail "${f##*/}"; done
shellcheck "$out"/bin/* tests/*.sh || fail shellcheck
# Every generated script runs under pipefail: a reader that stops early (head)
# kills its writer with SIGPIPE and the script with exit 141.
if grep -nE '[|][[:space:]]*head([[:space:]]|$)' "$out"/bin/*; then fail "a generated script pipes into head; under pipefail that exits 141. Use sed -n 1p or awk 'NR <= n'"; fi
golangci-lint config verify --config "$out/golangci.yml" || fail golangci.yml
grep -F "allow-parallel-runners: true" "$out/golangci.yml" || fail "golangci allow-parallel-runners"
grep -F "composer audit --locked" "$out/bin/dev-profile-contract-php" || fail "composer audit --locked"
if pkl eval -x 'checks["oxlint"].check' profile.pkl | grep -F -- "--deny-warnings"; then fail "oxlint must not deny-warnings"; fi
while IFS= read -r cmd; do [[ -x "$out/bin/$cmd" ]] || fail "hk step command without a rendered bin script: $cmd"; done < <(grep -ohE "dev-profile-[a-z0-9-]+" "$out/src/profile.pkl" "$out"/src/tools/*/*.pkl | sort -u)
pkl test tests/profile.test.pkl || fail "pkl test (regenerate the snapshot with: pkl test --overwrite tests/profile.test.pkl)"
bash tests/contract-fixtures.sh "$out" || fail "contract fixtures"
bash tests/go-fix-fixture.sh "$out" || fail "go-fix fixture"
bash tests/gosec-fixture.sh "$out" || fail "gosec fixture"
bash tests/go-mod-tidy-fixture.sh "$out" || fail "go-mod-tidy fixture"
bash tests/bump-fixture.sh "$out" || fail "bump fixture"
bash tests/modernizer-fixture.sh "$out" || fail "modernizer fixture"
bash tests/guards-fixture.sh "$out" || fail "guards fixture"
bash tests/deny-fixture.sh "$out" || fail "deny fixture"
bash tests/lint-full-tree-fixture.sh "$out" || fail "lint-full-tree fixture"
for gem_tool in bundle-audit brakeman; do command -v "$gem_tool" >/dev/null || echo "note: $gem_tool is not installed; run mise install (pinned in profile.pkl tools). Its push check is skipped until then."; done
bash tests/pr-fixture.sh "$out" || fail "pr fixture"
bash tests/escape-hatch-fixture.sh README.md "$out" || fail "escape-hatch fixture"
bash tests/sync-fixture.sh "$out" || fail "sync fixture"
bash tests/retire-fixture.sh "$out" || fail "retire fixture"
bash tests/shellcheck-fix-fixture.sh "$out" || fail "shellcheck-fix fixture"
bash tests/identity-guard-fixture.sh "$out" || fail "identity-guard fixture"
bash tests/owned-files-fixture.sh "$out" || fail "owned-files fixture"
bash tests/kernel-pins-fixture.sh "$out" || fail "kernel-pins fixture"
bash tests/retire-legacy-hooks-fixture.sh "$out" || fail "retire-legacy-hooks fixture"
bash tests/ci-action-fixture.sh "$out" || fail "ci-action fixture"
bash tests/lint-binding-fixture.sh "$out" || fail "lint-binding fixture"
echo "doctor ok"
