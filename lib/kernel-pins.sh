#!/usr/bin/env bash
set -euo pipefail
# Edit lib/kernel-pins.sh: `mise run generate` copies it into bin/ as dev-profile-kernel-pins.
# shellcheck source=/dev/null
source "$(dirname "${BASH_SOURCE[0]}")/../lib/facts.sh"

# mise ls --global lists what the rendered profile config requests, installed or not.
active="$(mise ls --global --json 2>/dev/null || echo '{}')"

# Neovim saves run the profile's dprint whatever this directory pins, so a
# different pin here makes `mise run fmt` and the editor format with different builds.
warn_dprint_here() { # <profile pin>
	local here
	here="$(mise ls --json dprint 2>/dev/null </dev/null | jq -r 'map(select(.active))[0].version // empty')" || return 0
	[[ -z "${here}" || "${here}" == "$1" || "${here}" == "$1".* ]] ||
		echo "doctor: this directory pins dprint ${here}; Neovim saves run the profile's ${1}, so they can format differently from mise run fmt" >&2
}

while read -r id pin; do
	if ! jq -e --arg id "${id}" --arg pin "${pin}" '(.[$id] // []) | any(.installed and .active and (.version == $pin or (.version | startswith($pin + "."))))' <<<"${active}" >/dev/null; then
		echo "doctor: ${id} ${pin} is pinned by the profile but is not the active installed version; run mise install" >&2
	fi
	[[ "${id}" != dprint ]] || warn_dprint_here "${pin}"
done <<<"${PROFILE_KERNEL_PINS:?}"
exit 0
