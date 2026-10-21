#!/usr/bin/env bash
# Contract fixtures for the node adapters: a pnpm lockfile runs through aube, and
# setup installs each workspace once, skipping vendored trees.
# Usage: node.sh <generated-dir>
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

fixture_nested_node_setup() {
	local repo
	repo="$(new_repo nested-node)"
	mkdir -p "${repo}/packages/ts" "${repo}/tests/runner" "${repo}/packages/ts/node_modules/dep"
	touch "${repo}/packages/ts/package-lock.json" "${repo}/tests/runner/aube-lock.yaml" \
		"${repo}/packages/ts/node_modules/dep/package-lock.json"
	echo '{}' >"${repo}/packages/ts/package.json"
	echo '{}' >"${repo}/tests/runner/package.json"
	run_task "$repo" setup || fail "nested node: setup failed"
	expect_call "aube|${repo}/packages/ts|install" "nested node"
	expect_call "aube|${repo}/tests/runner|install" "nested node"
	expect_no_call "node_modules/dep|install" "nested node"
}

fixture_pnpm
fixture_nested_node_setup
echo "contract node fixtures ok"
