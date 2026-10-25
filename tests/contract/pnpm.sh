#!/usr/bin/env bash
# Contract fixture for the pnpm lockfile adapter: a lockfile routes test through
# aube, and a package with no test script reports nothing to test.
# Usage: pnpm.sh <generated-dir>
set -euo pipefail
. "$(dirname "$0")/world.sh" "$@"

fixture_pnpm() {
	local with without
	with="$(new_repo pnpm-with-test)"
	touch "${with}/pnpm-lock.yaml"
	echo '{"scripts":{"test":"vitest"}}' >"${with}/package.json"
	run_task "$with" test || fail "pnpm with test: test failed"
	expect_call "aube|${with}|run test" "pnpm lockfile runs through aube"

	without="$(new_repo pnpm-without-test)"
	touch "${without}/pnpm-lock.yaml"
	echo '{"scripts":{"build":"tsc"}}' >"${without}/package.json"
	run_task "$without" test || fail "pnpm without test: test should pass"
	expect_no_call "run test" "pnpm without test"
	expect_output "nothing to test" "pnpm without test"
}

fixture_pnpm
echo "contract pnpm fixtures ok"
