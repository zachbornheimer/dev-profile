#!/usr/bin/env bash
# The identity guard against real git: a local identity or commit.gpgsign=false
# fails with the key to unset; global config alone passes.
# Usage: identity-guard-fixture.sh <generated-dir>
set -euo pipefail

out="${1:?usage: identity-guard-fixture.sh <generated-dir>}"
work="$(cd "$(mktemp -d)" && pwd -P)"
trap 'rm -rf "${work}"' EXIT
guard="${out}/bin/dev-profile-identity-guard"

fail() {
	echo "FAIL identity-guard fixture: $*" >&2
	[[ ! -f "${work}/output.txt" ]] || sed 's/^/  | /' "${work}/output.txt" >&2
	exit 1
}

# A repo whose config holds nothing local, and no global or system config to leak in.
export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_SYSTEM=/dev/null
repo="${work}/repo"
git init -q -b feature "$repo"
cd "$repo"

run_guard() { "$guard" >"${work}/output.txt" 2>&1; }

expect_rejected() { # <label> <expected message>
	if run_guard; then fail "$1: the guard must fail"; fi
	grep -Fq -- "$2" "${work}/output.txt" || fail "$1: expected message: $2"
}

run_guard || fail "no local identity: the guard must pass"

git config --local user.email t@example.com
expect_rejected "local user.email" \
	"identity-guard: local git config sets user.email; run: git config --local --unset user.email (identity comes from global config)"
git config --local --unset user.email
run_guard || fail "after unsetting user.email: the guard must pass"

git config --local user.name t
expect_rejected "local user.name" "run: git config --local --unset user.name"
git config --local --unset user.name

git config --local commit.gpgsign false
expect_rejected "commit.gpgsign=false" \
	"identity-guard: local git config sets commit.gpgsign=false; run: git config --local --unset commit.gpgsign (signing comes from global config)"
git config --local commit.gpgsign true
run_guard || fail "commit.gpgsign=true: the guard must pass"

echo "identity-guard fixture ok"
