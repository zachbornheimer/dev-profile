#!/usr/bin/env bash
set -euo pipefail
# Edit tools/css/stylelint-fix.sh: `mise run generate` copies it into bin/.

# stylelint --fix. Exit 2 = problems left for push; 78 = no config here.
(($#)) || exit 0
# shellcheck source=lib/sh/nearest-up.sh
source "$(dirname "${BASH_SOURCE[0]}")/../lib/nearest-up.sh"

if [[ -x "${root}/node_modules/.bin/stylelint" ]]; then
	stylelint="${root}/node_modules/.bin/stylelint"
elif command -v stylelint >/dev/null 2>&1; then
	stylelint="$(command -v stylelint)"
else
	exit 0
fi
code=0
"${stylelint}" --fix --allow-empty-input "$@" || code=$?
[[ "${code}" -le 2 || "${code}" -eq 78 ]] || exit "${code}"
