#!/usr/bin/env bash
# Guard fixtures for the commit hook itself: a clean change, a local-only git
# identity, shebang/executable mode, and a commit on the default branch.
# Usage: commit.sh <generated-dir>
set -euo pipefail
# Assigned by world.sh; declared here so this file lints on its own.
work=''
. "$(dirname "$0")/world.sh" "$@"

fixture_clean_change_passes() {
	local repo
	repo="$(new_repo clean)"
	echo "hello" >"${repo}/notes"
	git -C "$repo" add notes
	commit_hook "$repo" || fail "clean change: must pass"
}

fixture_local_identity_blocks() {
	local repo
	repo="$(new_repo local-identity)"
	echo "hello" >"${repo}/notes"
	git -C "$repo" add notes
	git -C "$repo" config user.email t@example.com
	expect_blocked "$repo" identity-guard "local git identity"
}

fixture_non_executable_script_is_fixed() {
	local repo mode
	repo="$(new_repo shebang-not-executable)"
	printf '#!/usr/bin/env bash\necho hi\n' >"${repo}/tool"
	chmod -x "${repo}/tool"
	git -C "$repo" add tool
	commit_hook "$repo" || fail "shebang script that is not executable: the fixer must pass"
	[[ -x "${repo}/tool" ]] || fail "shebang script that is not executable: worktree must be executable"
	mode="$(git -C "$repo" ls-files -s -- tool | awk '{print $1}')"
	[[ "${mode}" == "100755" ]] || fail "shebang script that is not executable: index mode ${mode}, want 100755"
}

fixture_executable_without_shebang_blocks() {
	local repo
	repo="$(new_repo executable-no-shebang)"
	echo "plain text" >"${repo}/tool"
	chmod +x "${repo}/tool"
	git -C "$repo" add tool
	expect_blocked "$repo" check-executables-have-shebangs "executable without a shebang"
}

fixture_default_branch_commit() {
	local repo remote
	remote="${work}/origin.git"
	git init -q --bare "$remote"
	repo="$(new_repo default-branch)"
	git -C "$repo" remote add origin "$remote"
	git -C "$repo" switch -q -c main
	echo "x" >"${repo}/notes"
	git -C "$repo" add notes
	expect_commit_blocked "$repo" "commit on main with an origin"
	DEV_PROFILE_ALLOW_DEFAULT_BRANCH_COMMIT=1 commit_hook "$repo" || fail "default branch: opt-out must pass"
	touch "$(git -C "$repo" rev-parse --path-format=absolute --git-path MERGE_HEAD)"
	commit_hook "$repo" || fail "default branch: finishing a merge must pass"
	rm -f "$(git -C "$repo" rev-parse --path-format=absolute --git-path MERGE_HEAD)"
	git -C "$repo" remote remove origin
	commit_hook "$repo" || fail "default branch: a repo without origin must pass"
}

fixture_clean_change_passes
fixture_local_identity_blocks
fixture_non_executable_script_is_fixed
fixture_executable_without_shebang_blocks
fixture_default_branch_commit
echo "guard commit fixtures ok"
