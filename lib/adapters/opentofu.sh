#!/usr/bin/env bash
set -euo pipefail
# Edit lib/adapters/opentofu.sh: `mise run generate` copies it into bin/ as dev-profile-contract-opentofu.
# Contract adapter: opentofu. Exit 0 ok, 1 failed, PROFILE_CONTRACT_NOTHING_TO_DO nothing to do.
verb="${1:?usage: dev-profile-contract-opentofu <verb>}"
# shellcheck source=lib/sh/contract-adapter.sh
source "$(dirname "${BASH_SOURCE[0]}")/../lib/contract-adapter.sh"

case "${verb}" in
lint)
	step tofu fmt -check -recursive
	step tflint --recursive
	step tofu init -backend=false -input=false
	step tofu validate
	;;
*) nothing_to_do ;;
esac
finish
