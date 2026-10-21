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
for alias in up pr pr-draft pr-auto "done"; do
	wt --config "$out/worktrunk.toml" config alias show "$alias" >/dev/null || fail "worktrunk alias $alias"
done
wt --config "$out/worktrunk.toml" config alias dry-run pr -- @ >/dev/null || fail worktrunk alias dry-run pr
grep -Fq "$out/bin/dev-profile-pkl-fmt" "$out/dprint.jsonc" || fail "dprint pkl exec must be $out/bin/dev-profile-pkl-fmt"
jq empty "$out/profile.json" || fail profile.json
luac -p "$out/conform.lua" || fail conform.lua
zsh -n "$out/shell.zsh" || fail shell.zsh
for f in "$out"/bin/*; do bash -n "$f" || fail "${f##*/}"; done
# Same bar the profile sets for every repo's push: warnings block, info tips do not.
# -x follows `source`, so tests/contract/*.sh are judged with their world.sh.
shellcheck -x --severity=warning "$out"/bin/* tests/*.sh tests/contract/*.sh || fail shellcheck
"$out/bin/dev-profile-git-config-hooks" || fail "git 2.54+ (config-based hooks) does not resolve"
# Every generated script runs under pipefail: a reader that stops early (head)
# kills its writer with SIGPIPE and the script with exit 141.
if grep -nE '[|][[:space:]]*head([[:space:]]|$)' "$out"/bin/*; then fail "a generated script pipes into head; under pipefail that exits 141. Use sed -n 1p or awk 'NR <= n'"; fi
golangci-lint config verify --config "$out/golangci.yml" || fail golangci.yml
grep -F "allow-parallel-runners: true" "$out/golangci.yml" || fail "golangci allow-parallel-runners"
grep -F "composer audit --locked" "$out/bin/dev-profile-contract-php" || fail "composer audit --locked"
# The `--deny-warnings` bar is an invariant `pkl test` below already evaluates,
# so it costs no second full evaluation of the profile here.
while IFS= read -r cmd; do [[ -x "$out/bin/$cmd" ]] || fail "hk step command without a rendered bin script: $cmd"; done < <(grep -ohE "dev-profile-[a-z0-9-]+" "$out/src/profile.pkl" "$out"/src/tools/*/*.pkl | sort -u)
pkl test tests/profile.test.pkl || fail "pkl test (regenerate the snapshot with: pkl test --overwrite tests/profile.test.pkl)"
bash tests/fixture-runner-test.sh || fail "fixture runner"
for gem_tool in bundle-audit brakeman; do command -v "$gem_tool" >/dev/null || echo "note: $gem_tool is not installed; run mise install (pinned in profile.pkl tools). Its push check is skipped until then."; done
# Every fixture builds its own repos under mktemp -d and reads this render
# read-only, so they run as a pool. The worker count is the core count, capped
# (tests/run-fixtures.sh); each failure is named with its own log.
fixtures=(
	tests/contract/go.sh
	tests/contract/hooks.sh
	tests/contract/dotnet.sh
	tests/contract/node.sh
	tests/contract/composer.sh
	tests/contract/overrides.sh
	tests/contract/runners.sh
	tests/contract/tasks.sh
	tests/contract/suppressions.sh
	tests/go-fix-fixture.sh
	tests/gosec-fixture.sh
	tests/go-mod-tidy-fixture.sh
	tests/bump-fixture.sh
	tests/modernizer-fixture.sh
	tests/perl-profile-fixture.sh
	tests/guards-fixture.sh
	tests/deny-fixture.sh
	tests/lint-full-tree-fixture.sh
	tests/pr-fixture.sh
	tests/escape-hatch-fixture.sh
	tests/sync-fixture.sh
	tests/done-fixture.sh
	tests/retire-fixture.sh
	tests/shellcheck-fix-fixture.sh
	tests/shellcheck-severity-fixture.sh
	tests/tool-path-fixture.sh
	tests/shell-init-fixture.sh
	tests/dev-family-fixture.sh
	tests/worktree-copy-fixture.sh
	tests/worktree-start-fixture.sh
	tests/identity-guard-fixture.sh
	tests/hardcoded-dev-port-fixture.sh
	tests/formatter-linter-agreement-fixture.sh
	tests/owned-files-fixture.sh
	tests/kernel-pins-fixture.sh
	tests/retire-legacy-hooks-fixture.sh
	tests/ci-action-fixture.sh
	tests/lint-binding-fixture.sh
)
bash tests/run-fixtures.sh "$out" "${fixtures[@]}" || fail "fixtures"
echo "doctor ok"
