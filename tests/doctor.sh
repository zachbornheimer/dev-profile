#!/usr/bin/env bash
# `mise run doctor`: syntax-check every generated file with the tool that consumes it.
set -euo pipefail
out="$DEV_PROFILE_OUT"
fail() {
	echo "FAIL: $*" >&2
	exit 1
}
for gem_tool in bundle-audit brakeman; do command -v "$gem_tool" >/dev/null || echo "note: $gem_tool is not installed; run mise install (pinned in profile.pkl tools). Its push check is skipped until then."; done
# Every check and fixture reads this render read-only and builds its own repos
# under mktemp -d, so they all run as one pool. The worker count is the core
# count, capped (tests/run-fixtures.sh); each failure is named with its own log.
# Longest first: the order decides only which jobs share the tail, and a slow job
# that starts last holds the whole run open alone. (Measured on a loaded 10-core Mac.)
queue=(
	tests/lint-binding/yaml.sh
	tests/lint-binding/json.sh
	tests/checks/hk-config.sh
	tests/checks/consumer-configs.sh
	tests/contract/node.sh
	tests/lint-binding/go.sh
	tests/sync-fixture.sh
	tests/pr-fixture.sh
	tests/contract/hooks.sh
	tests/lint-binding/lenient-json.sh
	tests/dev-family/restart.sh
	tests/dev-family/routes.sh
	tests/dev-family/state.sh
	tests/dev-family/markers.sh
	tests/dev-family/tether.sh
	tests/dev-family/escape-restart.sh
	tests/dev-family/escape-reap-path.sh
	tests/dev-family/route-labels.sh
	tests/dev-family/escape-reap-all.sh
	tests/checks/shellcheck.sh
	tests/retire-fixture.sh
	tests/perl-profile-fixture.sh
	tests/escape-hatch-fixture.sh
	tests/done-fixture.sh
	tests/guards/skip.sh
	tests/lint-full-tree-fixture.sh
	tests/hardcoded-dev-port-fixture.sh
	tests/guards/commit.sh
	tests/contract/go.sh
	tests/deny-fixture.sh
	tests/contract/tasks.sh
	tests/contract/runners.sh
	tests/guards/push.sh
	tests/gosec-fixture.sh
	tests/modernizer-fixture.sh
	tests/worktree-start-fixture.sh
	tests/worktree-copy-fixture.sh
	tests/contract/suppressions.sh
	tests/bump-fixture.sh
	tests/contract/overrides.sh
	tests/go-fix-fixture.sh
	tests/contract/dotnet.sh
	tests/guards/util.sh
	tests/retire-legacy-hooks-fixture.sh
	tests/contract/pnpm.sh
	tests/kernel-pins-fixture.sh
	tests/formatter-linter-agreement-fixture.sh
	tests/contract/composer.sh
	tests/ci-action-fixture.sh
	tests/fixture-runner-test.sh
	tests/checks/generated-files.sh
	tests/checks/profile-snapshot.sh
	tests/tool-path-fixture.sh
	tests/shellcheck-fix-fixture.sh
	tests/shell-init-fixture.sh
	tests/identity-guard-fixture.sh
	tests/go-mod-tidy-fixture.sh
	tests/shellcheck-severity-fixture.sh
	tests/owned-files-fixture.sh
)
bash tests/run-fixtures.sh "$out" "${queue[@]}" || fail "checks and fixtures"
echo "doctor ok"
