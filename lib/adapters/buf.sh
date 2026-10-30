#!/usr/bin/env bash
set -euo pipefail
# Edit lib/adapters/buf.sh: `mise run generate` copies it into bin/ as dev-profile-contract-buf.
# Contract adapter: buf. Exit 0 ok, 1 failed, PROFILE_CONTRACT_NOTHING_TO_DO nothing to do.
verb="${1:?usage: dev-profile-contract-buf <verb>}"
# shellcheck source=lib/sh/contract-adapter.sh
source "$(dirname "${BASH_SOURCE[0]}")/../lib/contract-adapter.sh"

# Every buf module (a dir holding buf.yaml), minus vendored copies.
modules() {
	local file
	git ls-files --cached --others --exclude-standard -- ':(glob)**/buf.yaml' |
		while IFS= read -r file; do
			case "/${file}" in */vendor/* | */node_modules/*) continue ;; esac
			dirname "${file}"
		done | sort -u
}

# Breaking changes are judged against the default branch, by absolute path.
breaking() {
	local dir="$1" top base
	top="$(git rev-parse --show-toplevel)"
	base="$(git rev-parse --abbrev-ref origin/HEAD 2>/dev/null)" || {
		echo "buf: no origin/HEAD; skipping breaking check in ${dir}" >&2
		return 0
	}
	step buf breaking "${dir}" --against "${top}/.git#branch=${base},subdir=${dir}"
}

case "${verb}" in
lint)
	while IFS= read -r dir; do
		step buf lint "${dir}"
		breaking "${dir}"
	done < <(modules)
	;;
build)
	while IFS= read -r dir; do
		if [[ -f "${dir}/buf.gen.yaml" ]]; then
			(cd "${dir}" && step buf generate && exit "${failed}") || failed=1
		fi
	done < <(modules)
	;;
*) nothing_to_do ;;
esac
finish
