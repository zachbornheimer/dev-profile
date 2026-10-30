#!/usr/bin/env bash
set -euo pipefail
# Edit lib/adapters/dotnet.sh: `mise run generate` copies it into bin/ as dev-profile-contract-dotnet.
# Contract adapter: dotnet. Exit 0 ok, 1 failed, PROFILE_CONTRACT_NOTHING_TO_DO nothing to do.
verb="${1:?usage: dev-profile-contract-dotnet <verb>}"
# shellcheck source=lib/sh/contract-adapter.sh
source "$(dirname "${BASH_SOURCE[0]}")/../lib/contract-adapter.sh"

# The solutions to drive (every .sln), or every project when a repo has none;
# dotnet needs one target per invocation, and nested projects are the norm.
targets() {
	local sln
	sln="$(git ls-files --cached --others --exclude-standard -- ':(glob)**/*.sln')"
	if [[ -n "${sln}" ]]; then
		echo "${sln}"
	else
		git ls-files --cached --others --exclude-standard -- ':(glob)**/*.csproj'
	fi | grep -vE '(^|/)(bin|obj)/' | sort -u
}

each_target() {
	local target ran=0
	while IFS= read -r target; do
		ran=$((ran + 1))
		step dotnet "$@" "${target}"
	done < <(targets)
	[[ "${ran}" -gt 0 ]] || nothing_to_do
}

case "${verb}" in
build) each_target build ;;
lint) each_target format --verify-no-changes ;;
test) each_target test ;;
*) nothing_to_do ;;
esac
finish
