#!/usr/bin/env bash
# DEV_PROFILE_OUT defaults to the live profile only at the default branch's tip.
# Any other commit renders into its own scratch directory, so a feature branch
# running doctor, lint or fmt cannot overwrite the live profile, and the tasks
# that link live configs refuse a scratch render.
# Usage: out-dir-fixture.sh
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
work="$(cd "$(mktemp -d)" && pwd -P)"
trap 'rm -rf "${work}"' EXIT

fail() {
	echo "FAIL out-dir fixture: $*" >&2
	exit 1
}

mkdir -p "${work}/home" "${work}/tmp"
live="${work}/home/.local/share/dev-profile"
scratch_prefix="${work}/tmp/dev-profile-out-"

# The helper finds its checkout from its own path, so each case gets a copy in a
# scratch repo. Hooks are off: the machine's global hooks reject a fixture commit.
git_in() { git -C "$1" -c core.hooksPath=/dev/null -c user.email=fixture@example.com -c user.name=fixture -c commit.gpgsign=false "${@:2}"; }
new_checkout() { # <dir>
	mkdir -p "$1/mise-tasks"
	cp "${here}/mise-tasks/out-dir" "$1/mise-tasks/out-dir"
	git -C "$1" init -q -b main
	git_in "$1" add -A
	git_in "$1" commit -q --no-verify -m init
}
out_dir() { # <checkout dir>
	HOME="${work}/home" TMPDIR="${work}/tmp" bash "$1/mise-tasks/out-dir"
}

repo="${work}/repo"
new_checkout "${repo}"

got="$(out_dir "${repo}")"
[[ "${got}" == "${live}" ]] || fail "the default branch tip must render to the live profile, got ${got}"

git_in "${repo}" switch -q -c feature
git_in "${repo}" commit -q --no-verify --allow-empty -m "feature work"
got="$(out_dir "${repo}")"
[[ "${got}" == "${scratch_prefix}"* ]] || fail "a feature branch must render to a scratch directory, got ${got}"
[[ "${got}" != "${live}" ]] || fail "a feature branch must never render to the live profile"
[[ "$(out_dir "${repo}")" == "${got}" ]] || fail "the scratch directory must be stable for a checkout"

git_in "${repo}" worktree add -q "${work}/second" -b second main
git_in "${repo}" worktree add -q "${work}/third" -b third main
git_in "${work}/third" commit -q --no-verify --allow-empty -m "more"
[[ "$(out_dir "${work}/third")" != "${got}" ]] || fail "two checkouts must not share a scratch directory"
[[ "$(out_dir "${work}/second")" == "${live}" ]] || fail "a second worktree at the default branch tip must render to the live profile"

git_in "${repo}" switch -q --detach main
[[ "$(out_dir "${repo}")" == "${live}" ]] || fail "a detached checkout at the default branch tip must render to the live profile"

plain="${work}/tarball"
mkdir -p "${plain}/mise-tasks"
cp "${here}/mise-tasks/out-dir" "${plain}/mise-tasks/out-dir"
[[ "$(out_dir "${plain}")" == "${live}" ]] || fail "a tree that is not a git checkout must render to the live profile"

# Linking live configs from a scratch render would point them at a directory that is cleaned up.
for task in bootstrap install-live; do
	if DEV_PROFILE_OUT="${scratch_prefix}abc123" PATH="${work}/none:/usr/bin:/bin" bash "${here}/mise-tasks/${task}" >"${work}/out.txt" 2>&1; then
		fail "${task} must refuse a scratch render"
	fi
	grep -Fq "scratch render" "${work}/out.txt" || fail "${task} must say why it refused"
done

echo "out-dir fixture ok"
