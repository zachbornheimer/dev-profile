#!/usr/bin/env bash
set -euo pipefail
# Edit tools/php/rector-fix.sh: `mise run generate` copies it into bin/.

# Rector rewrites PHP to the project's PHP-version set. The set lives in the
# repo's rector.php, so a repo without one opts out.
(($#)) || exit 0
# shellcheck source=lib/sh/nearest-up.sh
source "$(dirname "${BASH_SOURCE[0]}")/../lib/nearest-up.sh"

[[ -f "${root}/rector.php" ]] || exit 0
if [[ -x "${root}/vendor/bin/rector" ]]; then
	rector="${root}/vendor/bin/rector"
elif command -v rector >/dev/null 2>&1; then
	rector="$(command -v rector)"
else
	exit 0
fi
cd "${root}"
exec "${rector}" process --no-progress-bar --no-diffs --clear-cache --config rector.php "$@"
