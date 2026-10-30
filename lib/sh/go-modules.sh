# shellcheck shell=bash
# Sourced by the profile's bin/ scripts: `root`, `physical`, `nearest`, `gowork_for` and `packages`, for Go steps that
# group the given files by package and module.
# Edit lib/sh/go-modules.sh: `mise run generate` copies it into lib/.

root="$(cd "$(git rev-parse --show-toplevel)" && pwd -P)"

# Physical absolute path, so it compares equal to the paths go prints.
physical() {
	echo "$(cd "$(dirname "$1")" && pwd -P)/${1##*/}"
}

# The nearest directory at or above $1, up to the repo root, holding file $2.
nearest() {
	local dir="$1"
	while :; do
		if [[ -f "${dir}/$2" ]]; then
			echo "${dir}"
			return 0
		fi
		if [[ "${dir}" == "${root}" || "${dir}" == / ]]; then return 0; fi
		dir="$(dirname "${dir}")"
	done
}

# "off" when a go.work above the module does not list it: go would refuse to
# build it there ("directory is outside modules listed in go.work").
gowork_for() {
	local module="$1" workdir rel members
	workdir="$(nearest "${module}" go.work)"
	[[ -n "${workdir}" ]] || return 0
	rel="${module#"${workdir}"}"
	rel="${rel#/}"
	members="$(cd "${workdir}" && go work edit -json |
		jq -r '.Use[]?.DiskPath | sub("^\\./"; "") | sub("/$"; "") | if . == "" then "." else . end')"
	grep -qxF -- "${rel:-.}" <<<"${members}" || echo off
}

# The go tool ignores directories named testdata; so do we, since their
# files are fixtures that need not build.
under_testdata() {
	case "/${1#"${root}"}/" in */testdata/*) return 0 ;; esac
	return 1
}

# Staged Go files → one line per package: <module dir>, <GOWORK>, <package dir> joined by the unit separator (tab would collapse an empty GOWORK).
packages() {
	local file dir module
	for file in "$@"; do
		if [[ -f "${file}" ]]; then dirname "$(physical "${file}")"; fi
	done | sort -u | while IFS= read -r dir; do
		under_testdata "${dir}" && continue
		module="$(nearest "${dir}" go.mod)"
		[[ -n "${module}" ]] || continue
		printf '%s\x1f%s\x1f%s\n' "${module}" "$(gowork_for "${module}")" "${dir}"
	done | sort
}
