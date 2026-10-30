#!/usr/bin/env bash
set -euo pipefail
# Edit lib/commit-fix.sh: `mise run generate` copies it into bin/ as dev-profile-commit-fix.
# shellcheck source=lib/sh/real-wt.sh
source "$(dirname "${BASH_SOURCE[0]}")/../lib/real-wt.sh"
real=$(real_wt) || exit $?
status=0
"$real" "$@" || status=$?
if [ "$status" -ne 0 ]; then
	notice="wt step commit failed. Running: omp @task 'We were unable to run wt step commit due to errors. please fix, and then commit with wt step commit.'"
	zsh -fc 'print -ru2 -- "$1"' _ "$notice" || printf '%s\n' "$notice" >&2
	exec omp @task 'We were unable to run wt step commit due to errors. please fix, and then commit with wt step commit.'
fi
exit 0
