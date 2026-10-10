#!/usr/bin/env bash
# The doctor warning for profile-owned files: it names each one and still exits 0.
# Usage: owned-files-fixture.sh <generated-dir>
set -euo pipefail

out="${1:?usage: owned-files-fixture.sh <generated-dir>}"
work="$(cd "$(mktemp -d)" && pwd -P)"
trap 'rm -rf "${work}"' EXIT
warner="${out}/bin/dev-profile-owned-files"
export DEV_PROFILE_OUT="$out"

fail() {
	echo "FAIL owned-files fixture: $*" >&2
	[[ ! -f "${work}/output.txt" ]] || sed 's/^/  | /' "${work}/output.txt" >&2
	exit 1
}

new_repo() {
	mkdir -p "${work}/$1"
	echo "${work}/$1"
}

run_warner() { # <repo>: must exit 0
	(cd "$1" && "$warner") >"${work}/output.txt" 2>&1 || fail "$1: the warning must exit 0"
}

expect_warning() { # <label> <item>
	grep -Fq -- "doctor: $2 is profile-owned; delete it (README \"Repo contract\")" "${work}/output.txt" ||
		fail "$1: expected a warning for $2"
}

repo="$(new_repo clean)"
run_warner "$repo"
[[ ! -s "${work}/output.txt" ]] || fail "clean repo: no warning expected"

repo="$(new_repo prettier)"
echo '{}' >"${repo}/.prettierrc"
run_warner "$repo"
expect_warning "prettier config" ".prettierrc"

profile_go="$(sed -n 's/^go = "\(.*\)"$/\1/p' "${out}/mise-profile.toml")"
[[ -n "$profile_go" ]] || fail "the rendered profile has no go pin"
repo="$(new_repo runtime-pins)"
printf '[tools]\ngo = "%s"\nnode = "0"\n\n[tasks.x]\nrun = "true"\n' "$profile_go" >"${repo}/mise.toml"
run_warner "$repo"
expect_warning "go pin equal to the profile's" "mise.toml go = \"${profile_go}\""
if grep -Fq 'node' "${work}/output.txt"; then fail "a node pin that differs must not warn"; fi

echo "owned-files fixture ok"
