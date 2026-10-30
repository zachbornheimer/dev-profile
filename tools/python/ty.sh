#!/usr/bin/env bash
set -euo pipefail
# Edit tools/python/ty.sh: `mise run generate` copies it into bin/.

if ! command -v ty >/dev/null 2>&1; then
	exit 0
fi
ty check "$@"
