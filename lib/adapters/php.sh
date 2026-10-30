#!/usr/bin/env bash
set -euo pipefail
# Edit lib/adapters/php.sh: `mise run generate` copies it into bin/ as dev-profile-contract-php.
# Contract adapter: php. Exit 0 ok, 1 failed, PROFILE_CONTRACT_NOTHING_TO_DO nothing to do.
verb="${1:?usage: dev-profile-contract-php <verb>}"
# shellcheck source=lib/sh/contract-adapter.sh
source "$(dirname "${BASH_SOURCE[0]}")/../lib/contract-adapter.sh"

has_script() {
	jq -e --arg name "$1" '.scripts[$name] // empty' composer.json >/dev/null
}

case "${verb}" in
lint) step composer validate --no-check-publish ;;
test)
	if has_script test; then
		step composer run-script test
	elif [[ -x vendor/bin/phpunit ]]; then
		step vendor/bin/phpunit
	else
		nothing_to_do
	fi
	;;
scan)
	# `composer audit --locked` needs composer.lock; without one there is nothing to audit.
	if [[ -f composer.lock ]]; then
		step composer audit --locked
	else
		nothing_to_do
	fi
	;;
*) nothing_to_do ;;
esac
finish
