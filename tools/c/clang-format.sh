#!/usr/bin/env bash
set -euo pipefail
# Edit tools/c/clang-format.sh: `mise run generate` copies it into bin/.

if ! command -v clang-format >/dev/null 2>&1; then
	cat
	exit 0
fi
if [[ $# -eq 0 ]]; then
	clang-format
else
	clang-format -i "$@"
fi
