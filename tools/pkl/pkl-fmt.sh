#!/usr/bin/env bash
set -euo pipefail
# Edit tools/pkl/pkl-fmt.sh: `mise run generate` copies it into bin/.

# stdin → stdout. pkl exits 11 when it changed formatting; that is success here.
code=0
pkl format - || code=$?
[[ "${code}" -eq 0 || "${code}" -eq 11 ]] || exit "${code}"
