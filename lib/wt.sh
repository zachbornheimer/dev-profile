#!/usr/bin/env bash
set -euo pipefail
# Edit lib/wt.sh: `mise run generate` copies it into bin/ as wt.
# shellcheck source=lib/sh/real-wt.sh
source "$(dirname "${BASH_SOURCE[0]}")/../lib/real-wt.sh"
if [ -n "${COMPLETE:-}" ]; then
	real=$(real_wt) || exit $?
	exec "$real" "$@"
fi

# Sets WT_ARGS to the real wt argv with `--fix` removed. Returns 0 only
# when the command is `step commit` and `--fix` was present after it.
commit_fix_args() {
	local arg fix
	local -a kept
	WT_ARGS=()
	kept=()
	fix=0
	while [ $# -gt 0 ]; do
		arg=$1
		shift
		case "$arg" in
		--config=* | --config-set=*)
			kept[${#kept[@]}]=$arg
			;;
		-C | --config | --config-set)
			kept[${#kept[@]}]=$arg
			if [ $# -eq 0 ]; then
				return 1
			fi
			kept[${#kept[@]}]=$1
			shift
			;;
		--)
			return 1
			;;
		-*)
			kept[${#kept[@]}]=$arg
			;;
		step)
			if [ "${1:-}" != commit ]; then
				return 1
			fi
			kept[${#kept[@]}]=step
			kept[${#kept[@]}]=commit
			shift
			while [ $# -gt 0 ]; do
				arg=$1
				shift
				if [ "$arg" = -- ]; then
					kept[${#kept[@]}]=$arg
					while [ $# -gt 0 ]; do
						kept[${#kept[@]}]=$1
						shift
					done
					break
				fi
				if [ "$arg" = --fix ]; then
					fix=1
					continue
				fi
				kept[${#kept[@]}]=$arg
			done
			[ "$fix" -eq 1 ] || return 1
			WT_ARGS=("${kept[@]}")
			return 0
			;;
		*)
			return 1
			;;
		esac
	done
	return 1
}

if commit_fix_args "$@"; then
	exec "${0%/*}/dev-profile-commit-fix" "${WT_ARGS[@]}"
fi
real=$(real_wt) || exit $?
exec "$real" "$@"
