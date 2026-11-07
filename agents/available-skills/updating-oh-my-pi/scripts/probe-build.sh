#!/usr/bin/env bash
# probe-build.sh: run the omp-build assembly locally, the way CI merges it.
#
# Merges the fork's main plus the fork's configured branch list
# (one .toml per branch under fork/main:.omp-build/branches/, resolved by
# that commit's .omp-build/resolve-branches.ts) in order, using git
# merge-tree (the same ort merge `git merge --no-ff` runs in CI). It
# changes no branch: it only updates remote-tracking refs and writes
# unreferenced objects.
#
# The base is fork/main, the same commit CI assembles onto. fork/main is
# upstream main plus one carry commit. Commits it holds that upstream lacks
# may touch only .omp-build/ and .github/workflows/omp-build.yml.
#
# Usage: probe-build.sh [--base REF]... [--add BRANCH]... [--drop BRANCH]... [--repo PATH]
#   --base REF     assemble onto REF instead of fork/main (a 40-hex SHA or any
#                  rev the repo resolves; repeat to keep the last)
#   --add BRANCH   append BRANCH (must already be pushed to the fork)
#   --drop BRANCH  leave BRANCH out of this probe
#   --repo PATH    oh-my-pi checkout (default $OMP_REPO or ~/Developer/Personal/oh-my-pi)
# Exit: 0 every step merges cleanly; 1 a step conflicts, a branch is missing on
# the fork, or fork/main holds a non-carry commit; 2 usage or fetch error.
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
		sed -n '2,22p' "$0"
		exit 0
		;;
	*)
		echo "unknown argument: $1" >&2
		exit 2
		;;
	esac
done

cd "$repo"
git fetch -q origin main || exit 2
git fetch -q fork main || exit 2

command -v bun >/dev/null 2>&1 || {
	echo "bun is required to run .omp-build/resolve-branches.ts" >&2
	exit 2
}
staged="$(mktemp -d "${TMPDIR:-/tmp}/probe-omp-build.XXXXXX")"
trap 'rm -rf "$staged"' EXIT
git archive fork/main .omp-build | tar -x -C "$staged" || {
	echo "cannot materialize fork/main:.omp-build" >&2
	exit 2
}
resolver="$staged/.omp-build/resolve-branches.ts"
[ -f "$resolver" ] || {
	echo "cannot read fork/main:.omp-build/resolve-branches.ts" >&2
	exit 2
}
configured="$(bun "$resolver" "" schedule)" || {
	echo "fork/main .omp-build/branches failed to resolve via .omp-build/resolve-branches.ts:" >&2
	bun "$resolver" "" schedule >&2 || true
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
	# The base CI assembles onto: fork main, upstream plus the carry commit.
	upstream="$(git rev-parse refs/remotes/fork/main)"
	mb="$(git merge-base "$upstream" refs/remotes/origin/main)" || {
		echo "fork/main and origin/main have no merge-base" >&2
		exit 1
	}
	bad=0
	while IFS= read -r c; do
		[ -n "$c" ] || continue
		while IFS= read -r f; do
			[ -n "$f" ] || continue
			case "$f" in
			.omp-build/* | .github/workflows/omp-build.yml) ;;
			*)
				echo "fork/main holds a commit upstream main lacks outside the carry: ${c:0:10} $f" >&2
				bad=1
				;;
			esac
		done < <(git diff-tree --no-commit-id --name-only -r "$c")
	done < <(git rev-list "$mb..$upstream")
	[ "$bad" = 0 ] || exit 1
	behind="$(git rev-list --count "$upstream..refs/remotes/origin/main")"
	[ "$behind" = 0 ] || echo "note: fork/main is $behind commits behind upstream main (merge origin/main into it; do not push main by hand)" >&2
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
		cause="the upstream base"
	fi
	echo "  CONFLICT $b conflicts with $cause:"
	printf '%s\n' "$out" | tail -n +2 | sed 's/^/    /'
	exit 1
done
echo "assembly clean: ${#branches[@]} branches merge in order"
