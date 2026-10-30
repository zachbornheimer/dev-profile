#!/usr/bin/env bash
set -euo pipefail
# Edit lib/adapters/swift.sh: `mise run generate` copies it into bin/ as dev-profile-contract-swift.
# Contract adapter: swift. Exit 0 ok, 1 failed, PROFILE_CONTRACT_NOTHING_TO_DO nothing to do.
verb="${1:?usage: dev-profile-contract-swift <verb>}"
# shellcheck source=lib/sh/contract-adapter.sh
source "$(dirname "${BASH_SOURCE[0]}")/../lib/contract-adapter.sh"

case "${verb}" in
build) step swift build ;;
test) step swift test ;;
*) nothing_to_do ;;
esac
finish
