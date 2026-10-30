#!/usr/bin/env bash
set -euo pipefail
# Edit tools/javascript/oxlint-fix.sh: `mise run generate` copies it into bin/.

# Safe fixes plus suggestions (modernize); never --fix-dangerously.
# Exit 1 = diagnostics left for push; anything else is a real error.
code=0
oxlint --fix --fix-suggestions "$@" || code=$?
[[ "${code}" -le 1 ]] || exit "${code}"
