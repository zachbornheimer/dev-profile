# shellcheck shell=bash
# Sourced by the profile's bin/ scripts: `root`, `nearest_up <file> <glob>` and `absolute <file>`, for fixers that find a
# config or crate by walking up from a staged file.
# Edit lib/sh/nearest-up.sh: `mise run generate` copies it into lib/.

root="$(cd "$(git rev-parse --show-toplevel)" && pwd -P)"

# The nearest directory at or above file $1, up to the repo root, that holds a
# file matching glob $2. Prints nothing when there is none.
nearest_up() {
	local dir
	dir="$(cd "$(dirname "$1")" && pwd -P)"
	while :; do
		if compgen -G "${dir}/$2" >/dev/null; then
			echo "${dir}"
			return 0
		fi
		if [[ "${dir}" == "${root}" || "${dir}" == / ]]; then return 0; fi
		dir="$(dirname "${dir}")"
	done
}

# Absolute path of a staged file.
absolute() {
	echo "$(cd "$(dirname "$1")" && pwd -P)/$(basename "$1")"
}
