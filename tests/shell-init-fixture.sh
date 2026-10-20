#!/usr/bin/env bash
# The generated mise shell init: environment follows the directory, and an
# in-place mise.toml edit refreshes on the next prompt without a cd.
set -euo pipefail

out="${1:?usage: shell-init-fixture.sh <generated-dir>}"
work="$(cd "$(mktemp -d)" && pwd -P)"
trap 'rm -rf "${work}"' EXIT

project="${work}/project"
mkdir -p "${project}"
printf '[env]\nSHELL_INIT_TEST = "one"\n' >"${project}/mise.toml"

fail() {
	echo "FAIL shell-init fixture: $*" >&2
	exit 1
}

output="$(
cd "${project}" &&
	DEV_PROFILE_OUT="${out}" TEST_PROJECT="${project}" \
		MISE_TRUSTED_CONFIG_PATHS="${project}" \
		zsh -f -i -c '
				source "${DEV_PROFILE_OUT}/mise.zsh"
				print -r -- "start=${SHELL_INIT_TEST:-missing}"
				builtin cd /tmp
				_dev_profile_mise_refresh
				print -r -- "away=${SHELL_INIT_TEST:-missing}"
				builtin cd "${TEST_PROJECT}"
				_dev_profile_mise_refresh
				print -r -- "back=${SHELL_INIT_TEST:-missing}"
				printf "[env]\nSHELL_INIT_TEST = \"two\"\n" >mise.toml
				touch -t 203001010000 mise.toml
				_dev_profile_mise_refresh
				print -r -- "edited=${SHELL_INIT_TEST:-missing}"
			'
)" || fail "zsh shell init failed"

expect() { grep -qxF "$1" <<<"${output}" || fail "missing '$1' in: ${output}"; }
expect "start=one"
expect "away=missing"
expect "back=one"
expect "edited=two"
echo "shell-init fixture ok"
