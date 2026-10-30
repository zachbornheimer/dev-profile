#!/usr/bin/env bash
set -euo pipefail
# Edit lib/adapters/python.sh: `mise run generate` copies it into bin/ as dev-profile-contract-python.
# Contract adapter: python. Exit 0 ok, 1 failed, PROFILE_CONTRACT_NOTHING_TO_DO nothing to do.
verb="${1:?usage: dev-profile-contract-python <verb>}"
# shellcheck source=lib/sh/contract-adapter.sh
source "$(dirname "${BASH_SOURCE[0]}")/../lib/contract-adapter.sh"

pytest_no_tests=5

# pip-audit reads the locked requirements uv exports.
audit() {
	local requirements
	requirements="$(mktemp)"
	step uv export --frozen --format requirements-txt --no-hashes --output-file "${requirements}"
	step uvx pip-audit --disable-pip --no-deps -r "${requirements}"
	rm -f "${requirements}"
}

case "${verb}" in
build)
	grep -qF '[build-system]' pyproject.toml 2>/dev/null || nothing_to_do
	step uv build
	;;
test)
	code=0
	uv run --with pytest pytest || code=$?
	[[ "${code}" -ne "${pytest_no_tests}" ]] || nothing_to_do
	[[ "${code}" -eq 0 ]] || failed=1
	;;
scan) audit ;;
*) nothing_to_do ;;
esac
finish
