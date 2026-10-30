#!/usr/bin/env bash
set -euo pipefail
# Edit lib/contract.sh: `mise run generate` copies it into bin/ as dev-profile-contract.
# shellcheck source=/dev/null
source "$(dirname "${BASH_SOURCE[0]}")/../lib/facts.sh"

# Run every applicable contract adapter for one verb, from the repo root.
# Adapter exit: 0 ok, PROFILE_CONTRACT_NOTHING_TO_DO nothing to do, anything else failed.
verb="${1:?usage: dev-profile-contract <verb>}"
if ! root="$(git rev-parse --show-toplevel 2>/dev/null)"; then
	echo "dev-profile-contract: ${PWD} is not inside a git repository" >&2
	exit 2
fi
cd "${root}"

ran=0
failed=()

# True when the repo has a tracked or unignored file matching any pathspec.
has_marker() {
	[[ -n "$(git ls-files --cached --others --exclude-standard -- "$@")" ]]
}

run_adapter() {
	local id="$1" code=0
	"dev-profile-contract-${id}" "${verb}" || code=$?
	case "${code}" in
	0)
		ran=$((ran + 1))
		echo "ok    ${id} ${verb}"
		;;
	"${PROFILE_CONTRACT_NOTHING_TO_DO:?}")
		echo "skip  ${id} ${verb} (nothing to ${verb})"
		;;
	*)
		ran=$((ran + 1))
		failed+=("${id}")
		echo "FAIL  ${id} ${verb} (exit ${code})"
		;;
	esac
}

# PROFILE_CONTRACT_ADAPTERS: one "<id><TAB><globs>" line per adapter, in order; an
# adapter with no globs applies to every repo. Read on fd 3, so an adapter that
# reads stdin cannot eat the table.
while IFS=$'\t' read -r -u 3 id globs; do
	specs=()
	read -ra marks <<<"${globs}"
	for mark in "${marks[@]+"${marks[@]}"}"; do specs+=(":(glob)${mark}"); done
	if [[ "${#specs[@]}" -eq 0 ]] || has_marker "${specs[@]}"; then run_adapter "${id}"; fi
done 3<<<"${PROFILE_CONTRACT_ADAPTERS:?}"

if [[ "${ran}" -eq 0 ]]; then
	echo "nothing to ${verb}"
	exit 0
fi
if [[ "${#failed[@]}" -gt 0 ]]; then
	echo "${verb} failed: ${failed[*]}" >&2
	exit 1
fi
