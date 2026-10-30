#!/usr/bin/env bash
set -euo pipefail
# Edit tools/shared/fix.sh: `mise run generate` copies it into bin/.

# Run a fixer; exit 1 means "issues left for push to judge", not a failure.
code=0
"$@" || code=$?
[[ "${code}" -le 1 ]] || exit "${code}"
