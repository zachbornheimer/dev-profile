#!/usr/bin/env bash
set -euo pipefail
# Edit tools/shell/shellcheck-fix.sh: `mise run generate` copies it into bin/.

# Apply the fixes shellcheck is sure of to the staged shell files. Its parser
# understands heredocs, and it leaves expansions that may split on purpose
# ($(seq 3), ${CMD:-mise latest}) as warnings for a person, so a fix never
# changes what the script does. The pre-push shellcheck reports the rest.
if [[ $# -eq 0 ]]; then
	exit 0
fi
patch="$(shellcheck --format=diff "$@" 2>/dev/null || true)"
if [[ -z "${patch}" ]]; then
	exit 0
fi
git apply --whitespace=nowarn <<<"${patch}"
