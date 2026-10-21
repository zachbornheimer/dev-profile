#!/usr/bin/env bash
# Guard fixtures for the push-time checks: broken symlinks, added large files,
# and submodules. Usage: push.sh <generated-dir>
set -euo pipefail
. "$(dirname "$0")/world.sh" "$@"

fixture_broken_symlink_blocks() {
	local repo
	repo="$(new_repo broken-symlink)"
	ln -s missing-target "${repo}/link"
	git -C "$repo" add link
	expect_blocked "$repo" check-symlinks "broken symlink"
}

fixture_large_file_blocks() {
	local repo
	repo="$(new_repo large-file)"
	head -c 2000000 /dev/zero | tr '\0' 'a' >"${repo}/big.txt"
	git -C "$repo" add big.txt
	expect_blocked "$repo" check-added-large-files "large file"
}

fixture_large_lockfile_passes() {
	local repo
	repo="$(new_repo large-lockfile)"
	head -c 2000000 /dev/zero | tr '\0' 'a' >"${repo}/package-lock.json"
	git -C "$repo" add package-lock.json
	push_check "$repo" check-added-large-files || fail "large lockfile: must pass"
}

fixture_large_binary_still_blocks() {
	local repo
	repo="$(new_repo large-binary)"
	head -c 2000000 /dev/zero >"${repo}/blob.bin"
	git -C "$repo" add blob.bin
	expect_blocked "$repo" check-added-large-files "large binary"
}

fixture_gitmodules_blocks() {
	local repo
	repo="$(new_repo gitmodules)"
	printf '[submodule "s"]\n\tpath = s\n\turl = https://example.com/s.git\n' >"${repo}/.gitmodules"
	git -C "$repo" add .gitmodules
	git -C "$repo" update-index --add --cacheinfo "160000,$(printf '%040d' 1),s"
	expect_blocked "$repo" forbid-submodules "submodule"
}

fixture_broken_symlink_blocks
fixture_large_file_blocks
fixture_large_lockfile_passes
fixture_large_binary_still_blocks
fixture_gitmodules_blocks
echo "guard push fixtures ok"
