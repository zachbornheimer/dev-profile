#!/usr/bin/env bash
# What every check file in this directory shares, sourced: the `FAIL: <check>`
# line that names what broke. Each file owns its tools and reads the render
# read-only, so doctor runs them in the same pool as the fixtures.
# Usage (sourced): . common.sh
set -euo pipefail

# Sourced, never run: a check file that forgot to source this would otherwise
# look like a passing check that did nothing.
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
	echo 'common.sh is sourced by the check files in this directory; run those instead' >&2
	exit 2
fi

fail() {
	echo "FAIL: $*" >&2
	exit 1
}
