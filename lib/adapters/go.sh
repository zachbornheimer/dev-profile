#!/usr/bin/env bash
set -euo pipefail
# Edit lib/adapters/go.sh: `mise run generate` copies it into bin/ as dev-profile-contract-go.
# Contract adapter: go. Exit 0 ok, 1 failed, PROFILE_CONTRACT_NOTHING_TO_DO nothing to do.
verb="${1:?usage: dev-profile-contract-go <verb>}"
# shellcheck source=lib/sh/contract-adapter.sh
source "$(dirname "${BASH_SOURCE[0]}")/../lib/contract-adapter.sh"

# Every Go module (go.work members included), minus testdata and vendor copies.
modules() {
	local file
	git ls-files --cached --others --exclude-standard -- ':(glob)**/go.mod' |
		while IFS= read -r file; do
			case "/${file}" in */testdata/* | */vendor/*) continue ;; esac
			dirname "${file}"
		done | sort -u
}

# Modules go.work lists, as repo-relative dirs ("." for the root).
workspace_modules() {
	if [[ -f go.work ]]; then
		go work edit -json | jq -r '.Use[]?.DiskPath | sub("^\\./"; "") | if . == "" then "." else . end'
	fi
}

# Run one command in every module; the subshell's exit carries its step result.
# A module go.work does not list builds on its own go.mod (GOWORK=off); inside
# the workspace it would fail with "directory is outside modules listed in go.work".
each_module() {
	local dir members gowork
	members="$(workspace_modules)"
	while IFS= read -r dir; do
		gowork=""
		if [[ -f go.work ]] && ! grep -qxF -- "${dir}" <<<"${members}"; then gowork=off; fi
		echo "+ cd ${dir}${gowork:+ (GOWORK=off)}" >&2
		(cd "${dir}" && export GOWORK="${gowork}" && step "$@" && exit "${failed}") || failed=1
	done < <(modules)
}

case "${verb}" in
build) each_module go build ./... ;;
test) each_module go test ./... ;;
scan) each_module govulncheck ./... ;;
*) nothing_to_do ;;
esac
finish
