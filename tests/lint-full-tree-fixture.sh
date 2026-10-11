#!/usr/bin/env bash
# `hk check --all --slow --profile lint` (the lint verb) judges the whole tree:
# debt already on the upstream default branch still fails it, while the push
# ratchet keeps ignoring that same debt. Real hk, git and golangci-lint.
# Usage: lint-full-tree-fixture.sh <generated-dir>
set -euo pipefail

out="${1:?usage: lint-full-tree-fixture.sh <generated-dir>}"
work="$(cd "$(mktemp -d)" && pwd -P)"
trap 'rm -rf "${work}"' EXIT

fail() {
	echo "FAIL lint-full-tree fixture: $*" >&2
	exit 1
}

mkdir -p "${work}/hk-config"
ln -s "${out}/hk-config.pkl" "${work}/hk-config/config.pkl"
export PATH="${out}/bin:${PATH}"
unset HK_FILE
export GIT_AUTHOR_NAME=fixture GIT_AUTHOR_EMAIL=fixture@example.com GIT_COMMITTER_NAME=fixture GIT_COMMITTER_EMAIL=fixture@example.com

# A module whose default branch already carries a vet finding (an unchecked error, which
# go vet does not report, so only golangci-lint can fail the lint verb on it), on a clean feature branch: nothing is new since upstream.
# Hooks off for setup: the global config-based hooks would run the profile on the fixture push.
git_setup() { GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_SYSTEM=/dev/null git "$@"; }

new_clone_with_upstream_debt() {
	local origin="${work}/origin.git" repo="${work}/repo"
	git_setup init -q --bare -b main "$origin"
	git_setup clone -q "$origin" "$repo" 2>/dev/null
	git_setup -C "$repo" switch -q -c main
	printf 'module fixture\n\ngo 1.24\n' >"${repo}/go.mod"
	printf 'package fixture\n\nimport "os"\n\nfunc Clean() { os.Remove("scratch") }\n' >"${repo}/clean.go"
	git_setup -C "$repo" add -A
	git_setup -C "$repo" commit -q --no-verify -m "feat: debt"
	git_setup -C "$repo" push -q origin main
	git_setup -C "$repo" fetch -q origin
	git_setup -C "$repo" switch -q -c feature
	echo "$repo"
}

repo="$(new_clone_with_upstream_debt)"

if (cd "$repo" && HK_CONFIG_DIR="${work}/hk-config" hk check --all --slow --profile lint) >"${work}/lint.txt" 2>&1; then
	cat "${work}/lint.txt" >&2
	fail "lint must fail on debt already on the upstream default branch"
fi
grep -q 'errcheck' "${work}/lint.txt" || {
	cat "${work}/lint.txt" >&2
	fail "lint failed, but not on golangci-lint errcheck"
}

(cd "$repo" && dev-profile-golangci-ratchet) >"${work}/ratchet.txt" 2>&1 || fail "the push ratchet must still ignore upstream debt"

echo "lint-full-tree fixture ok"
