#!/usr/bin/env bash
set -euo pipefail
# Edit tools/c/clang-tidy.sh: `mise run generate` copies it into bin/.

# clang-tidy modernize-* findings, judged at push. Needs compile_commands.json beside the file, in a
# parent directory, or in a build/ directory; without one there is nothing to do.
(($#)) || exit 0
command -v clang-tidy >/dev/null 2>&1 || exit 0
# shellcheck source=lib/sh/nearest-up.sh
source "$(dirname "${BASH_SOURCE[0]}")/../lib/nearest-up.sh"

database_dir() {
	local dir
	dir="$(nearest_up "$1" compile_commands.json)"
	if [[ -n "${dir}" ]]; then
		echo "${dir}"
		return 0
	fi
	dir="$(nearest_up "$1" build/compile_commands.json)"
	if [[ -n "${dir}" ]]; then echo "${dir}/build"; fi
}

failed=0
for file in "$@"; do
	abs="$(absolute "${file}")"
	db="$(database_dir "${abs}")"
	[[ -n "${db}" ]] || continue
	# Exit is non-zero for files outside the database; only a modernize finding fails.
	out="$(clang-tidy -p "${db}" --checks='-*,modernize-*' --quiet "${abs}" 2>&1 || true)"
	if grep -Eq 'warning: .*\[modernize-' <<<"${out}"; then
		echo "${out}" >&2
		failed=1
	fi
done
exit "${failed}"
