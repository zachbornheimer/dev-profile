#!/usr/bin/env bash
set -euo pipefail
# Edit tools/dotnet/dotnet-format-fix.sh: `mise run generate` copies it into bin/.

# `dotnet format` style and analyzer fixes, limited to the staged files of each
# solution or project.
(($#)) || exit 0
command -v dotnet >/dev/null 2>&1 || exit 0
# shellcheck source=lib/sh/nearest-up.sh
source "$(dirname "${BASH_SOURCE[0]}")/../lib/nearest-up.sh"

for file in "$@"; do
	abs="$(absolute "${file}")"
	dir="$(nearest_up "${abs}" '*.sln')"
	[[ -n "${dir}" ]] || dir="$(nearest_up "${abs}" '*.csproj')"
	[[ -n "${dir}" ]] || continue
	printf '%s\x1f%s\n' "${dir}" "${abs}"
done | sort | {
	current=""
	files=()
	flush() {
		[[ -n "${current}" ]] || return 0
		(cd "${current}" && dotnet format --no-restore --include "${files[@]}") || true
	}
	while IFS=$'\x1f' read -r dir abs; do
		if [[ "${dir}" != "${current}" ]]; then
			flush
			current="${dir}"
			files=()
		fi
		files+=("${abs}")
	done
	flush
}
