#!/usr/bin/env bash
# probe-build.sh: run the omp-build assembly locally, the way CI merges it.
#
# Merges the pinned upstream base plus the fork's configured branch list
# (fork/ci:.github/omp-rebuild.toml) in order, using git merge-tree (the same
# ort merge `git merge --no-ff` runs in CI). It changes no branch: it only
# updates remote-tracking refs and writes unreferenced objects.
#
# The base is the pin in fork/ci:.github/omp-upstream.txt — the same commit CI
# assembles onto — not upstream main HEAD; a probe never fails merely because
# upstream moved. Without the pin it falls back to origin/main.
#
# Usage: probe-build.sh [--base REF]... [--add BRANCH]... [--drop BRANCH]... [--repo PATH]
#   --base REF     assemble onto REF instead of the pin (a 40-hex SHA or any
#                  rev the repo resolves; repeat to keep the last)
#   --add BRANCH   append BRANCH (must already be pushed to the fork)
#   --drop BRANCH  leave BRANCH out of this probe
#   --repo PATH    oh-my-pi checkout (default $OMP_REPO or ~/Developer/Personal/oh-my-pi)
# Exit: 0 every step merges cleanly; 1 a step conflicts or a branch is
# missing on the fork; 2 usage or fetch error.
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
		sed -n '2,15p' "$0"
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
git fetch -q fork ci || exit 2

configured="$(git show fork/ci:.github/omp-rebuild.toml | sed 's/#.*//' | sed -n '/^branches *= *\[/,/\]/p' | grep -oE '"[^"]+"' | tr -d '"')"

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
	# The pin CI assembles onto; without it, upstream main HEAD.
	upstream="$(git show fork/ci:.github/omp-upstream.txt 2>/dev/null | grep -m1 -oE '^[0-9a-f]{40}$' || true)"
	if [ -z "$upstream" ]; then
		upstream="$(git rev-parse refs/remotes/origin/main)"
		echo "no pin in fork/ci:.github/omp-upstream.txt: falling back to upstream main ${upstream:0:10}" >&2
	fi
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
		cur="$(git commit-tree --no-gpg-sign "$(printf '%s\n' "$out" | head -1)" -p "$cur" -p "$ref" -m "probe: merge $b")"
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
