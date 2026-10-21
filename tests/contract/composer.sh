#!/usr/bin/env bash
# Contract fixture for the composer adapters: test runs the composer script, and
# scan audits only when a lockfile is committed, plus the secret scan.
# Usage: composer.sh <generated-dir>
set -euo pipefail
# Assigned by world.sh; declared here so this file lints on its own.
log=''
. "$(dirname "$0")/world.sh" "$@"

fixture_composer() {
	local repo
	repo="$(new_repo composer)"
	echo '{"scripts":{"test":"phpunit"}}' >"${repo}/composer.json"
	run_task "$repo" test || fail "composer: test failed"
	expect_call "composer|${repo}|run-script test" "composer"
	commit_all "$repo"
	run_task "$repo" scan || fail "composer without lock: scan failed"
	expect_no_call "audit --locked" "composer without lock"
	echo '{}' >"${repo}/composer.lock"
	commit_all "$repo"
	run_task "$repo" scan || fail "composer: scan failed"
	expect_call "composer|${repo}|audit --locked" "composer with lock"
	grep -qF "gitleaks|${repo}|dir --redact --no-banner " "$log" ||
		fail "composer: expected a gitleaks scan of the tracked tree"
}

fixture_composer
echo "contract composer fixtures ok"
