#!/usr/bin/env bash
set -euo pipefail
# Edit lib/adapters/node.sh: `mise run generate` copies it into bin/ as dev-profile-contract-node.
# Contract adapter: node. Exit 0 ok, 1 failed, PROFILE_CONTRACT_NOTHING_TO_DO nothing to do.
verb="${1:?usage: dev-profile-contract-node <verb>}"
# shellcheck source=lib/sh/contract-adapter.sh
source "$(dirname "${BASH_SOURCE[0]}")/../lib/contract-adapter.sh"

# Every package with its own lockfile, nested ones included (mise deps only
# sees the repo root), minus installed copies.
packages() {
	local file
	git ls-files --cached --others --exclude-standard -- ':(glob)**/aube-lock.yaml' ':(glob)**/pnpm-lock.yaml' ':(glob)**/package-lock.json' ':(glob)**/yarn.lock' ':(glob)**/bun.lock' ':(glob)**/bun.lockb' |
		while IFS= read -r file; do
			case "/${file}" in */node_modules/*) continue ;; esac
			dirname "${file}"
		done | sort -u
}

# aube runs npm, pnpm and aube projects (it reads their lockfiles); yarn and
# bun lockfiles keep their own tool. Run from inside the package.
package_manager() {
	if [[ -f bun.lock || -f bun.lockb ]]; then
		echo bun
	elif [[ -f yarn.lock ]]; then
		echo yarn
	else
		echo aube
	fi
}

has_script() {
	[[ -f package.json ]] && jq -e --arg name "$1" '.scripts[$name] // empty' package.json >/dev/null
}

# Run one step in every package; a script verb skips packages without it.
ran=0
each_package() {
	local dir script="${1:-}"
	shift
	while IFS= read -r dir; do
		if [[ -n "${script}" ]] && ! (cd "${dir}" && has_script "${script}"); then continue; fi
		ran=$((ran + 1))
		echo "+ cd ${dir}" >&2
		(cd "${dir}" && step "$(package_manager)" "$@" && exit "${failed}") || failed=1
	done < <(packages)
	[[ "${ran}" -gt 0 ]] || nothing_to_do
}

case "${verb}" in
setup) each_package "" install ;;
build) each_package build run build ;;
lint) each_package lint run lint ;;
test) each_package test run test ;;
scan) each_package "" audit ;;
*) nothing_to_do ;;
esac
finish
