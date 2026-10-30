#!/usr/bin/env bash
set -euo pipefail
# Edit lib/adapters/perl.sh: `mise run generate` copies it into bin/ as dev-profile-contract-perl.
# Contract adapter: perl. Exit 0 ok, 1 failed, PROFILE_CONTRACT_NOTHING_TO_DO nothing to do.
verb="${1:?usage: dev-profile-contract-perl <verb>}"
# shellcheck source=lib/sh/contract-adapter.sh
source "$(dirname "${BASH_SOURCE[0]}")/../lib/contract-adapter.sh"

case "${verb}" in
test)
	[[ -d t ]] || nothing_to_do
	step prove -lr t
	;;
*) nothing_to_do ;;
esac
finish
