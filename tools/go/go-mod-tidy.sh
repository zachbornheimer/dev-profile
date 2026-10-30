#!/usr/bin/env bash
set -euo pipefail
# Edit tools/go/go-mod-tidy.sh: `mise run generate` copies it into bin/.

# go mod tidy for every module that owns one of the given files, run from the
# module directory. A module a parent go.work omits gets GOWORK=off, as the
# other Go steps do. --diff: report instead of rewrite (push).
mode="tidy"
if [[ "${1:-}" == "--diff" ]]; then
	mode="diff"
	shift
fi
(($#)) || exit 0
# shellcheck source=lib/sh/go-modules.sh
source "$(dirname "${BASH_SOURCE[0]}")/../lib/go-modules.sh"

failed=0
while IFS=$'\x1f' read -r module gowork; do
	if [[ "${mode}" == diff ]]; then
		(cd "${module}" && GOWORK="${gowork}" go mod tidy -diff) || failed=1
	else
		(cd "${module}" && GOWORK="${gowork}" go mod tidy) || failed=1
	fi
done < <(packages "$@" | cut -d $'\x1f' -f 1,2 | sort -u)
exit "${failed}"
