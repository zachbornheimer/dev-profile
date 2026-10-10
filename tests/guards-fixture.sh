#!/usr/bin/env bash
# Commit guards and supply-chain wrappers, against real git and the generated hk
# config. Usage: guards-fixture.sh <generated-dir>
set -euo pipefail

out="${1:?usage: guards-fixture.sh <generated-dir>}"
work="$(cd "$(mktemp -d)" && pwd -P)"
trap 'rm -rf "${work}"' EXIT

fail() {
	echo "FAIL guards fixture: $*" >&2
	[[ ! -f "${work}/output.txt" ]] || sed 's/^/  | /' "${work}/output.txt" >&2
	exit 1
}

mkdir -p "${work}/hk-config"
ln -s "${out}/hk-config.pkl" "${work}/hk-config/config.pkl"
export PATH="${out}/bin:${PATH}"
unset HK_FILE

new_repo() {
	local dir="${work}/$1"
	mkdir -p "$dir"
	git -C "$dir" init -q -b feature
	# The generated dprint config, so the dprint step never depends on a global
	# config this machine may or may not have. Untracked: hk sees staged files only.
	cp "${out}/dprint.jsonc" "${dir}/dprint.jsonc"
	echo "$dir"
}

# The commit hook, as git runs it for a staged change.
commit_hook() {
	(cd "$1" && HK_CONFIG_DIR="${work}/hk-config" hk run pre-commit --staged) >"${work}/output.txt" 2>&1
}

expect_blocked() {
	local repo="$1" label="$2"
	if commit_hook "$repo"; then fail "${label}: the commit must be blocked"; fi
}

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
	expect_blocked "$repo" "local git identity"
}

fixture_broken_symlink_blocks() {
	local repo
	repo="$(new_repo broken-symlink)"
	ln -s missing-target "${repo}/link"
	git -C "$repo" add link
	expect_blocked "$repo" "broken symlink"
}

fixture_non_executable_script_blocks() {
	local repo
	repo="$(new_repo shebang-not-executable)"
	printf '#!/usr/bin/env bash\necho hi\n' >"${repo}/tool"
	chmod -x "${repo}/tool"
	git -C "$repo" add tool
	expect_blocked "$repo" "shebang script that is not executable"
}

fixture_executable_without_shebang_blocks() {
	local repo
	repo="$(new_repo executable-no-shebang)"
	echo "plain text" >"${repo}/tool"
	chmod +x "${repo}/tool"
	git -C "$repo" add tool
	expect_blocked "$repo" "executable without a shebang"
}

fixture_large_file_blocks() {
	local repo
	repo="$(new_repo large-file)"
	head -c 2000000 /dev/zero | tr '\0' 'a' >"${repo}/big.txt"
	git -C "$repo" add big.txt
	expect_blocked "$repo" "large file"
}

fixture_large_lockfile_passes() {
	local repo
	repo="$(new_repo large-lockfile)"
	head -c 2000000 /dev/zero | tr '\0' 'a' >"${repo}/package-lock.json"
	git -C "$repo" add package-lock.json
	commit_hook "$repo" || fail "large lockfile: must pass"
}

fixture_large_binary_still_blocks() {
	local repo
	repo="$(new_repo large-binary)"
	head -c 2000000 /dev/zero >"${repo}/blob.bin"
	git -C "$repo" add blob.bin
	expect_blocked "$repo" "large binary"
}

fixture_gitmodules_blocks() {
	local repo
	repo="$(new_repo gitmodules)"
	printf '[submodule "s"]\n\tpath = s\n\turl = https://example.com/s.git\n' >"${repo}/.gitmodules"
	git -C "$repo" add .gitmodules
	git -C "$repo" update-index --add --cacheinfo "160000,$(printf '%040d' 1),s"
	expect_blocked "$repo" "submodule"
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
	expect_blocked "$repo" "commit on main with an origin"
	DEV_PROFILE_ALLOW_DEFAULT_BRANCH_COMMIT=1 commit_hook "$repo" || fail "default branch: opt-out must pass"
	touch "$(git -C "$repo" rev-parse --path-format=absolute --git-path MERGE_HEAD)"
	commit_hook "$repo" || fail "default branch: finishing a merge must pass"
	rm -f "$(git -C "$repo" rev-parse --path-format=absolute --git-path MERGE_HEAD)"
	git -C "$repo" remote remove origin
	commit_hook "$repo" || fail "default branch: a repo without origin must pass"
}

fixture_if_installed() {
	local ran="${work}/ran"
	dev-profile-if-installed definitely-not-installed-tool touch "$ran" || fail "if-installed: absent tool must skip"
	[[ ! -e "$ran" ]] || fail "if-installed: absent tool must not run the command"
	dev-profile-if-installed bash touch "$ran" || fail "if-installed: present tool must run"
	[[ -e "$ran" ]] || fail "if-installed: present tool must run the command"
	if dev-profile-if-installed bash false; then fail "if-installed: a failing command must fail"; fi
}

# gosec scans the whole package, but only findings in the pushed files block.
fixture_gosec_changed_files_only() {
	command -v gosec >/dev/null 2>&1 || return 0
	local repo
	repo="$(new_repo gosec)"
	mkdir -p "${repo}/pkg"
	printf 'module example.com/fixture\n\ngo 1.22\n' >"${repo}/go.mod"
	printf 'package pkg\n\nfunc Clean() int { return 1 }\n' >"${repo}/pkg/clean.go"
	printf 'package pkg\n\nimport "math/rand"\n\nfunc Roll() int { return rand.Intn(6) }\n' >"${repo}/pkg/dirty.go"
	(cd "$repo" && dev-profile-gosec-packages pkg/clean.go) >"${work}/output.txt" 2>&1 ||
		fail "gosec: a clean changed file must pass despite a dirty untouched file"
	if (cd "$repo" && dev-profile-gosec-packages pkg/dirty.go) >"${work}/output.txt" 2>&1; then
		fail "gosec: a dirty changed file must fail"
	fi
	grep -q 'pkg/dirty.go:5 G404' "${work}/output.txt" || fail "gosec: the finding must be printed"
}

fixture_if_installed
fixture_gosec_changed_files_only
fixture_clean_change_passes
fixture_local_identity_blocks
fixture_broken_symlink_blocks
fixture_non_executable_script_blocks
fixture_executable_without_shebang_blocks
fixture_large_file_blocks
fixture_large_lockfile_passes
fixture_large_binary_still_blocks
fixture_gitmodules_blocks
fixture_default_branch_commit
echo "guards fixture ok"
