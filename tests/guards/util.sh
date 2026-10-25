#!/usr/bin/env bash
# Guard fixtures for the wrappers themselves: if-installed skips an absent tool,
# and gosec judges only the pushed files. Usage: util.sh <generated-dir>
set -euo pipefail
# Assigned by world.sh; declared here so this file lints on its own.
work=''
. "$(dirname "$0")/world.sh" "$@"

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
echo "guard util fixtures ok"
