#!/usr/bin/env bash
set -euo pipefail
# Edit tools/shared/if-installed.sh: `mise run generate` copies it into bin/.

# dev-profile-if-installed <tool> <command…>: run the command only when <tool>
# is on PATH (mise shims count). A missing scanner is not a failure.
tool="${1:?usage: dev-profile-if-installed <tool> <command…>}"
shift
command -v "${tool}" >/dev/null 2>&1 || exit 0
exec "$@"
