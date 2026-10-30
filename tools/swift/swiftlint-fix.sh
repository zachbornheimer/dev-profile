#!/usr/bin/env bash
set -euo pipefail
# Edit tools/swift/swiftlint-fix.sh: `mise run generate` copies it into bin/.

if ! command -v swiftlint >/dev/null 2>&1; then
	exit 0
fi
if [[ $# -eq 0 ]]; then
	exit 0
fi
exec dev-profile-fix swiftlint --fix --quiet "$@"
