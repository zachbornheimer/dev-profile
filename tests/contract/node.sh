#!/usr/bin/env bash
# Contract fixture for setup in a node repo: each workspace installs once and
# vendored node_modules stay untouched. Usage: node.sh <generated-dir>
set -euo pipefail
. "$(dirname "$0")/world.sh" "$@"

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

fixture_nested_node_setup
echo "contract node fixtures ok"
