#!/usr/bin/env bash
# The CI action's contract, offline: with the rendered profile linked where the
# action (and bootstrap) links it, a repo outside every code root gets the profile's
# pins and the contract tasks, and a repo pin still wins.
# Usage: ci-action-fixture.sh <generated-dir>
set -euo pipefail

out="${1:?usage: ci-action-fixture.sh <generated-dir>}"
work="$(cd "$(mktemp -d)" && pwd -P)"
trap 'rm -rf "${work}"' EXIT
repo_pin="1.25"

fail() {
	echo "FAIL ci-action fixture: $*" >&2
	exit 1
}

# A runner's home: only the link the action makes, nothing of this machine's.
home="${work}/home"
mkdir -p "${home}"
HOME="${home}" "${out}/bin/dev-profile-env" --config-dir "${home}/.config/mise" --link-only
export HOME="${home}" XDG_CONFIG_HOME="${home}/.config" MISE_TRUSTED_CONFIG_PATHS="${work}"
unset MISE_GLOBAL_CONFIG_FILE

mkdir -p "${work}/bare" "${work}/pinned"
printf '[tasks.ci]\nrun = "true"\n' >"${work}/bare/mise.toml"
printf '[tools]\ngo = "%s"\n' "${repo_pin}" >"${work}/pinned/mise.toml"

requested_go() { # <repo>: the go version mise would use there
	(cd "$1" && mise ls --current --json go | jq -r '.[0].requested_version')
}

profile_go="$(sed -n 's/^go = "\(.*\)"$/\1/p' "${out}/mise-profile.toml")"
[[ -n "${profile_go}" ]] || fail "no go pin in ${out}/mise-profile.toml"
got="$(cd "${work}" && mise ls --current --json go | jq -r '.[0].requested_version')"
[[ "${got}" == "${profile_go}" ]] || fail "a directory without mise.toml got go '${got}', want the profile's '${profile_go}'"
got="$(requested_go "${work}/bare")"
[[ "${got}" == "${profile_go}" ]] || fail "repo without a go pin got '${got}', want the profile's '${profile_go}'"
got="$(requested_go "${work}/pinned")"
[[ "${got}" == "${repo_pin}" ]] || fail "repo go pin '${repo_pin}' must override the profile, got '${got}'"

# `mise run profile:ci` resolves outside a code root, and every tool the profile
# pins (the ones hk steps invoke, markdownlint and betterleaks among them) has a
# version there: a shim for a tool no active config pins fails "no version set".
(cd "${work}" && mise tasks --json | jq -e 'any(.[]; .name == "profile:ci")' >/dev/null) ||
	fail "profile:ci is not a task outside a code root"
pinned="$(awk '/^\[tools\]/{t=1; next} /^\[/{t=0} t && /=/{gsub(/"/, "", $1); print $1}' "${out}/mise-profile.toml")"
[[ -n "${pinned}" ]] || fail "no [tools] in ${out}/mise-profile.toml"
active="$(cd "${work}" && mise ls --current --json | jq -r 'keys[]')"
for tool in ${pinned} npm:markdownlint-cli betterleaks; do
	grep -Fxq -- "${tool}" <<<"${active}" || fail "${tool} has no version outside a code root"
done

# The local entry gives a clone outside every code root the same context, from an
# isolated config dir under the cache, and leaves the live ~/.config alone.
env_bin="${out}/bin/dev-profile-env"
unset XDG_CONFIG_HOME
export DEV_PROFILE_CACHE="${work}/cache"
(cd "${work}/bare" && "${env_bin}" -- mise tasks --json | jq -e 'any(.[]; .name == "profile:ci")' >/dev/null) ||
	fail "dev-profile-env: profile:ci must resolve"
active="$(cd "${work}/bare" && "${env_bin}" -- mise ls --current --json | jq -r 'keys[]')"
for tool in npm:markdownlint-cli betterleaks; do
	grep -Fxq -- "${tool}" <<<"${active}" || fail "dev-profile-env: ${tool} has no version"
done
root_env="$(cd "${work}/bare" && "${env_bin}" --root personal -- mise env --json | jq -r '.DEV_PROFILE // empty')"
[[ "${root_env}" == personal ]] || fail "dev-profile-env --root personal must load the personal overlay, got '${root_env}'"
[[ -L "${work}/cache/env-personal/conf.d/root-overlay.toml" ]] || fail "dev-profile-env must write only under the cache dir"
if "${env_bin}" --root nowhere -- true 2>/dev/null; then fail "dev-profile-env: an unknown root must fail"; fi
echo "ci-action fixture ok"
