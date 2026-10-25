#!/usr/bin/env bash
# The world every guard fixture runs in, sourced by the files in this directory:
# one throwaway tree of repos, the generated hk config, and the run helpers that
# drive a commit hook or one push-time step. Each file owns its world, so doctor
# runs them as a pool.
# Usage (sourced): . world.sh <generated-dir>
set -euo pipefail

# Sourced, never run: a fixture file that forgot to source this would otherwise
# look like a passing fixture that did nothing.
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
	echo 'world.sh is sourced by the guard fixture files in this directory; run those instead' >&2
	exit 2
fi

out="${1:?usage: <fixture>.sh <generated-dir>}"
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

# Judge-only guards run at push, not commit. `hk check --slow --staged` runs them
# over the staged files, one step at a time; plumbing makes the base commit with no hooks involved.
push_check() {
	local repo="$1" step="$2"
	git -C "$repo" rev-parse -q --verify HEAD >/dev/null 2>&1 ||
		git -C "$repo" update-ref HEAD "$(GIT_AUTHOR_NAME=fixture GIT_AUTHOR_EMAIL=fixture@example.com GIT_COMMITTER_NAME=fixture GIT_COMMITTER_EMAIL=fixture@example.com git -C "$repo" commit-tree -m init "$(git -C "$repo" hash-object -t tree -w /dev/null)")"
	(cd "$repo" && HK_CONFIG_DIR="${work}/hk-config" hk check --slow --staged -S "$step") >"${work}/output.txt" 2>&1
}

expect_blocked() {
	local repo="$1" step="$2" label="$3"
	if push_check "$repo" "$step"; then fail "${label}: the push check must block"; fi
}

expect_commit_blocked() {
	local repo="$1" label="$2"
	if commit_hook "$repo"; then fail "${label}: the commit must be blocked"; fi
}
