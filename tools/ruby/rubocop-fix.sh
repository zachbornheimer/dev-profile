#!/usr/bin/env bash
set -euo pipefail
# Edit tools/ruby/rubocop-fix.sh: `mise run generate` copies it into bin/.

if ! command -v rubocop >/dev/null 2>&1; then
	exit 0
fi
if [[ $# -eq 0 ]]; then
	exit 0
fi
# -A includes unsafe cops (modernize). Exit 1 = offenses left for push; 2 = real error.
code=0
rubocop -A --fail-level F "$@" || code=$?
[[ "${code}" -le 1 ]] || exit "${code}"
