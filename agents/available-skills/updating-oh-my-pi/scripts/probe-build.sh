#!/usr/bin/env bash
# probe-build.sh: run the omp-build assembly locally, the way CI merges it.
#
# Merges the fork's main plus the fork's configured branch list in order,
# using git merge-tree (the same ort merge `git merge --no-ff` runs in CI).
# The list is the directory fork/main:.omp-build/branches/ (one TOML file per
# branch), resolved by the fork's own .omp-build/resolve-branches.ts, which
# this script extracts from fork/main with `git archive` and runs under bun.
# It changes no branch: it only updates remote-tracking refs and writes
# unreferenced objects.
#
# The base is fork/main, the same commit CI assembles onto: upstream main plus
# the carry commit(s) holding the build machinery. A probe is therefore only
# meaningful against the fork's current main; advance it with
# sync-fork-main.sh.
#
# Usage: probe-build.sh [--base REF]... [--add BRANCH]... [--drop BRANCH]... [--repo PATH]
#   --base REF     assemble onto REF instead of fork/main (a 40-hex SHA or any
#                  rev the repo resolves; repeat to keep the last)
#   --add BRANCH   append BRANCH (must already be pushed to the fork)
#   --drop BRANCH  leave BRANCH out of this probe
#   --repo PATH    oh-my-pi checkout (default $OMP_REPO or ~/Developer/Personal/oh-my-pi)
# Exit: 0 every step merges cleanly; 1 a step conflicts or a branch is missing
# on the fork; 2 usage, fetch or branch-list error.
set -euo pipefail

repo="${OMP_REPO:-$HOME/Developer/Personal/oh-my-pi}"
adds=()
drops=()
bases=()
while [ $# -gt 0 ]; do
	case "$1" in
	--add | --drop | --repo | --base)
		[ $# -ge 2 ] || {
			echo "$1 needs a value" >&2
			exit 2
		}
		case "$1" in
		--add) adds+=("$2") ;;
		--drop) drops+=("$2") ;;
		--repo) repo="$2" ;;
		--base) bases+=("$2") ;;
		esac
		shift 2
		;;
	-h | --help)
		sed -n '2,24p' "$0"
		exit 0
		;;
	*)
		echo "unknown argument: $1" >&2
		exit 2
		;;
	esac
done

cd "$repo"
git fetch -q fork main || exit 2

command -v bun >/dev/null 2>&1 || {
	echo "bun is required to run .omp-build/resolve-branches.ts" >&2
	exit 2
}
buildroot="$(mktemp -d "${TMPDIR:-/tmp}/probe-build.XXXXXX")"
trap 'rm -rf "$buildroot"' EXIT
git archive refs/remotes/fork/main .omp-build 2>/dev/null | tar -x -C "$buildroot" || {
	echo "cannot read .omp-build from fork/main" >&2
	exit 2
}
[ -f "$buildroot/.omp-build/resolve-branches.ts" ] || {
	echo "no .omp-build/resolve-branches.ts on fork/main" >&2
	exit 2
}
configured="$(bun "$buildroot/.omp-build/resolve-branches.ts" "" workflow_dispatch 2>/dev/null)" || {
	echo "fork/main .omp-build/branches failed to resolve via resolve-branches.ts:" >&2
	bun "$buildroot/.omp-build/resolve-branches.ts" "" workflow_dispatch >&2 || true
	exit 2
}

branches=()
while IFS= read -r b; do
	[ -n "$b" ] || continue
	keep=1
	for d in ${drops[@]+"${drops[@]}"}; do
		[ "$b" = "$d" ] && keep=0
	done
	[ "$keep" = 1 ] && branches+=("$b")
done <<<"$configured"
for a in ${adds[@]+"${adds[@]}"}; do
	present=0
	for b in ${branches[@]+"${branches[@]}"}; do
		[ "$b" = "$a" ] && present=1
	done
	[ "$present" = 1 ] || branches+=("$a")
done

if [ ${#branches[@]} -eq 0 ]; then
	echo "no branches: CI refuses this (Branchless assembly)" >&2
	exit 1
fi

if [ "${#bases[@]}" -gt 0 ]; then
	upstream="${bases[${#bases[@]}-1]}"
	git rev-parse --verify -q "$upstream^{commit}" >/dev/null || {
		echo "--base $upstream does not resolve to a commit" >&2
		exit 2
	}
else
	# The base CI assembles onto: the fork's main (upstream plus the carry commit).
	upstream="$(git rev-parse refs/remotes/fork/main)"
fi
cur="$upstream"
echo "upstream base ${upstream:0:10}"
for b in "${branches[@]}"; do
	ref="refs/remotes/fork/$b"
	if ! git fetch -q fork "+refs/heads/$b:$ref" 2>/dev/null; then
		echo "  MISSING  $b is not on the fork (push it first)"
		exit 1
	fi
	rc=0
	out="$(git merge-tree --write-tree --name-only --no-messages "$cur" "$ref")" || rc=$?
	if [ "$rc" = 0 ]; then
		# The merge commit is synthetic and unreferenced, so it carries the probe's own
		# identity: git otherwise needs the caller's config, and a hermetic checkout
		# (GIT_CONFIG_GLOBAL=/dev/null, a runner whose GECOS field is empty) has no name
		# to fall back to and dies with "empty ident name".
		cur="$(GIT_AUTHOR_NAME=probe GIT_AUTHOR_EMAIL=probe@example.invalid \
			GIT_COMMITTER_NAME=probe GIT_COMMITTER_EMAIL=probe@example.invalid \
			git commit-tree --no-gpg-sign "$(printf '%s\n' "$out" | head -1)" -p "$cur" -p "$ref" -m "probe: merge $b")"
		echo "  clean    $b"
		continue
	fi
	[ "$rc" = 1 ] || exit 2
	if [ "$cur" != "$upstream" ] && git merge-tree --write-tree --name-only --no-messages "$upstream" "$ref" >/dev/null; then
		cause="an earlier branch in the list (it merges cleanly onto the base alone)"
	else
		cause="the base (fork main)"
	fi
	echo "  CONFLICT $b conflicts with $cause:"
	printf '%s\n' "$out" | tail -n +2 | sed 's/^/    /'
	exit 1
done
echo "assembly clean: ${#branches[@]} branches merge in order"
