#!/usr/bin/env bash
# Contract fixtures for a repo's own task file: a verb that does nothing, an
# override, an extension of the profile verb, and a failure that still runs the
# other adapters. Usage: overrides.sh <generated-dir>
set -euo pipefail
. "$(dirname "$0")/world.sh" "$@"

fixture_no_ecosystem() {
	local repo
	repo="$(new_repo no-ecosystem)"
	run_task "$repo" test || fail "no ecosystem: test should pass"
	expect_output "nothing to test" "no ecosystem"
	run_task "$repo" build || fail "no ecosystem: build should pass"
	expect_output "nothing to build" "no ecosystem"
}

fixture_override_and_extend() {
	local override extend
	override="$(new_repo override)"
	echo "module o" >"${override}/go.mod"
	printf '[tasks.test]\nrun = "echo repo-override"\n' >"${override}/mise.toml"
	run_task "$override" test || fail "override: test failed"
	expect_output "repo-override" "override"
	expect_no_call "test ./..." "override"

	extend="$(new_repo extend)"
	echo "module e" >"${extend}/go.mod"
	printf '[tasks.test]\ndepends = ["profile:test"]\nrun = "echo repo-extend"\n' >"${extend}/mise.toml"
	run_task "$extend" test || fail "extend: test failed"
	expect_output "repo-extend" "extend"
	expect_call "go|${extend}|test ./..." "extend"
}

fixture_failure_runs_every_adapter() {
	local repo
	repo="$(new_repo failure)"
	echo "module f" >"${repo}/go.mod"
	touch "${repo}/pnpm-lock.yaml"
	echo '{"scripts":{"test":"vitest"}}' >"${repo}/package.json"
	if STUB_FAIL=go run_task "$repo" test; then fail "failure: test should fail"; fi
	expect_output "FAIL  go test" "failure"
	expect_call "aube|${repo}|run test" "failure"
}

fixture_no_ecosystem
fixture_override_and_extend
fixture_failure_runs_every_adapter
echo "contract override fixtures ok"
