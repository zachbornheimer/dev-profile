#!/usr/bin/env bash
# Contract fixtures for the global git hooks: hook skew, the commit guard, and
# the lint verb on a default branch. Usage: hooks.sh <generated-dir>
set -euo pipefail
# Assigned by world.sh; declared here so this file lints on its own.
work='' output=''
. "$(dirname "$0")/world.sh" "$@"

fixture_git_hook_skips_undefined_hook() {
	local repo stale="${work}/stale-hk-config" msg="${work}/commit-msg.txt"
	repo="$(new_repo hook-skew)"
	mkdir -p "$stale"
	printf 'amends "%s"\nhooks { ["pre-push"] { steps { ["noop"] { check = "true" } } } }\n' \
		"package://github.com/jdx/hk/releases/download/v2.5.0/hk@2.5.0#/Config.pkl" >"${stale}/config.pkl"
	echo "feat: add thing" >"$msg"
	HK_CONFIG_DIR="$stale" run_hook "$repo" commit-msg "$msg" || fail "hook skew: an undefined hook must not fail"
	expect_output "mise bootstrap --from" "hook skew"
	echo "not conventional" >"$msg"
	if run_hook "$repo" commit-msg "$msg"; then fail "hook skew: a defined hook's failure must still block"; fi
	expect_output "subject must be" "hook skew"
}

# A clean repo on its default branch with an origin, the shape CI and `mise run lint` see.
new_published_default_branch_repo() {
	local repo
	repo="$(new_repo "$1")"
	git -C "$repo" checkout -q -b main
	git -C "$repo" remote add origin "https://example.invalid/${1}.git"
	commit_all "$repo"
	echo "$repo"
}

fixture_lint_ignores_commit_guards_on_default_branch() {
	local repo
	repo="$(new_published_default_branch_repo lint-on-main)"
	HK_CONFIG_DIR="${work}/hk-config" run_task "$repo" lint ||
		fail "lint on default branch: a commit-only guard failed the lint verb"
}

fixture_commit_guard_still_blocks_commit_on_default_branch() {
	local repo
	repo="$(new_published_default_branch_repo commit-on-main)"
	echo change >>"${repo}/README.md"
	git -C "$repo" add -A
	if run_hook "$repo" pre-commit --staged; then fail "commit guard: a commit on the default branch was allowed"; fi
	expect_output "protected branch" "commit guard"
}

fixture_hk_fix_on_default_branch() {
	local repo
	repo="$(new_published_default_branch_repo hk-fix-on-main)"
	(cd "$repo" && HK_CONFIG_DIR="${work}/hk-config" hk fix --all) >"$output" 2>&1 ||
		fail "hk fix on default branch: must pass"
	if grep -qF "protected branch" "$output"; then
		fail "hk fix on default branch: printed protected branch"
	fi
}

fixture_hk_check_on_default_branch() {
	local repo
	repo="$(new_published_default_branch_repo hk-check-on-main)"
	(cd "$repo" && HK_CONFIG_DIR="${work}/hk-config" hk check --all) >"$output" 2>&1 || true
	if grep -qF "protected branch" "$output"; then
		fail "hk check on default branch: failed because of no-commit-to-branch"
	fi
}

fixture_git_hook_skips_undefined_hook
fixture_lint_ignores_commit_guards_on_default_branch
fixture_commit_guard_still_blocks_commit_on_default_branch
fixture_hk_fix_on_default_branch
fixture_hk_check_on_default_branch
echo "contract hook fixtures ok"
