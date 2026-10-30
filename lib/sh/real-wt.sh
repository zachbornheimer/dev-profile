# shellcheck shell=bash
# Sourced by the commit-fix scripts: `real_wt` prints the worktrunk binary on PATH,
# skipping the generated `wt` wrapper beside the calling script ($0).
# Edit lib/sh/real-wt.sh: `mise run generate` copies it into lib/.

real_wt() {
	local dir cand self_dir rest
	self_dir=$(cd "$(dirname "$0")" && pwd -P) || return 127
	rest=$PATH
	while [ -n "$rest" ]; do
		dir=${rest%%:*}
		case $rest in
		*:*) rest=${rest#*:} ;;
		*) rest= ;;
		esac
		[ -n "$dir" ] || continue
		cand=$dir/wt
		[ -x "$cand" ] || continue
		[ "$cand" -ef "$self_dir/wt" ] && continue
		printf '%s\n' "$cand"
		return 0
	done
	printf '%s\n' 'wt: no worktrunk binary on PATH' >&2
	return 127
}
