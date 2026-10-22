#!/usr/bin/env bash
# The world every lint-binding fixture runs in, sourced by the files in this
# directory: an empty HOME with the render linked in as a runner's would be, a
# PATH without the profile's bin dir, a decoy hk config on that HOME, and the
# helpers that make a repo and run `profile:lint` in it through the runner or the
# isolated local entry. Each file owns its world, so doctor runs them as a pool.
#
# `profile:lint` must lint with the rendered profile's hk and dprint config in a
# context that has no ~/.config of its own: a runner (empty HOME, the action's
# link) and the isolated local entry (dev-profile-env) in a clone outside every
# code root.
# Usage (sourced): . world.sh <generated-dir>
set -euo pipefail

# Sourced, never run: a fixture file that forgot to source this would otherwise
# look like a passing fixture that did nothing.
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
	echo 'world.sh is sourced by the lint-binding fixture files in this directory; run those instead' >&2
	exit 2
fi

out="${1:?usage: <fixture>.sh <generated-dir>}"
work="$(cd "$(mktemp -d)" && pwd -P)"
trap 'rm -rf "${work}"' EXIT

fail() {
	echo "FAIL lint-binding fixture: $*" >&2
	[[ ! -f "${work}/output.txt" ]] || sed 's/^/  | /' "${work}/output.txt" >&2
	exit 1
}

# Tool installs and caches stay shared with this machine; the home does not.
real_home="${HOME}"
export MISE_DATA_DIR="${MISE_DATA_DIR:-${real_home}/.local/share/mise}"
export MISE_CACHE_DIR="${MISE_CACHE_DIR:-${real_home}/Library/Caches/mise}"
export MISE_STATE_DIR="${MISE_STATE_DIR:-${real_home}/.local/state/mise}"
export DPRINT_CACHE_DIR="${DPRINT_CACHE_DIR:-${real_home}/Library/Caches/dprint}"
[[ -d "${MISE_CACHE_DIR}" ]] || export MISE_CACHE_DIR="${real_home}/.cache/mise"
[[ -d "${DPRINT_CACHE_DIR}" ]] || export DPRINT_CACHE_DIR="${real_home}/.cache/dprint"
home="${work}/home"
mkdir -p "${home}"
export HOME="${home}" XDG_CONFIG_HOME="${home}/.config" XDG_STATE_HOME="${home}/.local/state"
export MISE_TRUSTED_CONFIG_PATHS="${work}" DEV_PROFILE_CACHE="${work}/cache"
unset MISE_GLOBAL_CONFIG_FILE MISE_CONFIG_DIR HK_CONFIG_DIR DPRINT_CONFIG_DIR YAMLLINT_CONFIG_FILE
# State of the `mise run` that launched this: a runner's mise starts without it.
while IFS= read -r name; do unset "${name}"; done < <(compgen -e | grep -E '^(__MISE_|MISE_(TASK_|PROJECT_ROOT|CONFIG_ROOT|ORIGINAL_CWD))')

# A runner starts without the profile's bin dir on PATH, however this machine's
# mise activation or the launching `mise run` spelled it.
clean_path=""
while IFS= read -r -d: entry || [[ -n "${entry}" ]]; do
	entry="${entry%$'\n'}"
	[[ ! -e "${entry}/dev-profile-contract" ]] || continue
	clean_path="${clean_path:+${clean_path}:}${entry}"
done <<<"${PATH}"
export PATH="${clean_path}"

new_repo() { # <name>
	local dir="${work}/$1"
	mkdir -p "${dir}"
	git -C "${dir}" init -q -b feature
	printf '[tasks.noop]\nrun = "true"\n' >"${dir}/mise.toml"
	echo "${dir}"
}

# Run `mise run profile:lint` in <repo> through <context>: runner or entry.
lint() { # <context> <repo>
	case "$1" in
	runner) (cd "$2" && mise run profile:lint) ;;
	entry) (cd "$2" && "${out}/bin/dev-profile-env" -- mise run profile:lint) ;;
	esac >"${work}/output.txt" 2>&1
}

"${out}/bin/dev-profile-env" --config-dir "${home}/.config/mise" --link-only

# The rendered config puts the render's bin dir on PATH (`[env] _.path`), as "~/..."
# when the render sits under HOME. The action renders under the runner's HOME, so
# give this empty home the same render instead of leaning on this machine's PATH.
render_link="${home}/.local/share/dev-profile"
if grep -q '^path = \[ "~/.local/share/dev-profile/bin" \]' "${out}/mise-profile.toml"; then
	mkdir -p "$(dirname "${render_link}")"
	ln -sfn "${out}" "${render_link}"
fi

# A machine with its own hk config (a Mac) must not leak it into the lint: this
# decoy fails every repo, so a clean repo passes only if the render's config wins.
mkdir -p "${home}/.config/hk"
cat >"${home}/.config/hk/config.pkl" <<'PKL'
amends "package://github.com/jdx/hk/releases/download/v2.5.0/hk@2.5.0#/Config.pkl"
hooks { ["check"] { steps { ["decoy-live-config"] { check = "false" } } } }
PKL
