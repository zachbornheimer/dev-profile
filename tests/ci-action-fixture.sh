#!/usr/bin/env bash
# The CI action's contract, offline: with the rendered profile as mise's global
# config, a repo with no go pin gets the profile's go, and a repo pin wins.
# Usage: ci-action-fixture.sh <generated-dir>
set -euo pipefail

out="${1:?usage: ci-action-fixture.sh <generated-dir>}"
work="$(cd "$(mktemp -d)" && pwd -P)"
trap 'rm -rf "${work}"' EXIT
export MISE_GLOBAL_CONFIG_FILE="${out}/mise-profile.toml"
export MISE_TRUSTED_CONFIG_PATHS="${work}"
repo_pin="1.25"

fail() {
	echo "FAIL ci-action fixture: $*" >&2
	exit 1
}

requested_go() { # <repo>: the go version mise would use there
	(cd "$1" && mise ls --current --json go | jq -r '.[0].requested_version')
}

profile_go="$(sed -n 's/^go = "\(.*\)"$/\1/p' "${MISE_GLOBAL_CONFIG_FILE}")"
[[ -n "${profile_go}" ]] || fail "no go pin in ${MISE_GLOBAL_CONFIG_FILE}"

mkdir -p "${work}/bare" "${work}/pinned"
printf '[tasks.ci]\nrun = "true"\n' >"${work}/bare/mise.toml"
printf '[tools]\ngo = "%s"\n' "${repo_pin}" >"${work}/pinned/mise.toml"

got="$(requested_go "${work}/bare")"
[[ "${got}" == "${profile_go}" ]] || fail "repo without a go pin got '${got}', want the profile's '${profile_go}'"
got="$(requested_go "${work}/pinned")"
[[ "${got}" == "${repo_pin}" ]] || fail "repo go pin '${repo_pin}' must override the profile, got '${got}'"
