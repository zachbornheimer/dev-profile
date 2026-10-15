#!/usr/bin/env bash
# `profile:lint` must lint with the rendered profile's hk and dprint config in a
# context that has no ~/.config of its own: a runner (empty HOME, the action's
# link) and the isolated local entry (dev-profile-env) in a clone outside every
# code root. A repo with invalid JSON, or a Go printf mismatch, must fail; a clean
# repo must pass, so the failure is the file's and not the environment's.
# Usage: lint-binding-fixture.sh <generated-dir>
set -euo pipefail

out="${1:?usage: lint-binding-fixture.sh <generated-dir>}"
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

clean="$(new_repo clean)"
printf '{\n  "a": 1\n}\n' >"${clean}/data.json"
printf '%s\n' 'action: zachbornheimer/dev-profile@6376251df9c4df0b7063464303b5de1b833fabad # immutable action revision' >"${clean}/data.yaml"
bad="$(new_repo bad-inputs)"
printf '{"a": }\n' >"${bad}/data.json"
printf '{"a": 1,}\n' >"${bad}/trailing.json"
printf 'key: one\nkey: two\n' >"${bad}/data.yaml"

# Red control: with the PATH binding stripped from the rendered config the contract
# scripts are not found, so a clean repo must fail; the runs below pass only through it.
mkdir -p "${work}/stripped/conf.d"
grep -v '^path = ' "${out}/mise-profile.toml" >"${work}/stripped/conf.d/dev-profile.toml"
if (cd "${clean}" && MISE_CONFIG_DIR="${work}/stripped" mise run profile:lint) >"${work}/output.txt" 2>&1; then
	fail "runner: a clean repo passed profile:lint with the PATH binding stripped"
fi

for context in runner entry; do
	lint "${context}" "${clean}" || fail "${context}: a clean repo must pass profile:lint"
done

# A SHA-pinned action exceeds yamllint's default 80-column limit. The profile's
# generated policy permits it and does not require a YAML document marker.
# The clean repo above includes a SHA-pinned action over yamllint's default
# 80-column limit. Its success checks the generated YAML policy in both contexts.

# Red control: without the binding, hk sees yamllint's defaults instead of the
# rendered policy.
mkdir -p "${work}/yaml-unbound/conf.d"
grep -v '^YAMLLINT_CONFIG_FILE = ' "${out}/mise-profile.toml" >"${work}/yaml-unbound/conf.d/dev-profile.toml"
if (cd "${clean}" && MISE_CONFIG_DIR="${work}/yaml-unbound" mise run profile:lint) >"${work}/output.txt" 2>&1; then
	fail "runner: valid YAML passed with the yamllint binding stripped"
fi
grep -q 'line-length' "${work}/output.txt" || fail "runner: the unbound control must fail yamllint's default line-length rule"

# One failing run exercises the JSON parser, strict JSON check and YAML duplicate
# rule together; both contexts must report all three defects.
for context in runner entry; do
	if lint "${context}" "${bad}"; then fail "${context}: invalid JSON and YAML must fail profile:lint"; fi
	grep -q 'data.json' "${work}/output.txt" || fail "${context}: the parser failure must name data.json"
	grep -q 'not strict JSON.*trailing.json\|trailing.json.*not strict JSON' "${work}/output.txt" || fail "${context}: strict JSON must name trailing.json"
	grep -q 'key-duplicates' "${work}/output.txt" || fail "${context}: yamllint must report duplicate keys"
done

if command -v golangci-lint >/dev/null 2>&1 && command -v go >/dev/null 2>&1; then
	bad_go="$(new_repo bad-go)"
	printf 'module example.com/fixture\n\ngo 1.22\n' >"${bad_go}/go.mod"
	printf 'package main\n\nimport "fmt"\n\nfunc main() { fmt.Printf("%%d\\n", "text") }\n' >"${bad_go}/main.go"
	if lint entry "${bad_go}"; then fail "entry: a Go printf mismatch must fail profile:lint"; fi
fi
echo "lint-binding fixture ok"
