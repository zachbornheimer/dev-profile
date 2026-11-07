#!/usr/bin/env bash
# sync-fork-main.sh: merge upstream main into the fork's main.
#
# The fork's `main` is upstream main plus the carry commit(s) that hold the
# build machinery (.github/workflows/omp-build.yml, .omp-build/). GitHub's
# merge-upstream API merges upstream into fork main; the `main-protected`
# ruleset blocks only deletion and force-push, so no bypass is needed.
#
# Safety: when fork main already contains upstream main (identical or ahead of
# it) nothing is done. Otherwise a backup tag `backup/fork-main-<UTC>` is
# recorded on the fork, merge-upstream runs, and main is verified to contain
# upstream's pre-sync tip. A 409 from the API means upstream changed files the
# carry commit also touches: main is left unchanged and you resolve it by hand.
#
# Usage: sync-fork-main.sh [--fork OWNER/REPO] [--upstream OWNER/REPO]
# Exit: 0 main contains upstream main; 1 sync refused or failed;
# 2 usage or API error.
set -euo pipefail

fork="${OMP_FORK:-zachbornheimer/oh-my-pi}"
upstream="${OMP_UPSTREAM:-can1357/oh-my-pi}"

while [ $# -gt 0 ]; do
	case "$1" in
	--fork | --upstream)
		[ $# -ge 2 ] || {
			echo "$1 needs a value" >&2
			exit 2
		}
		case "$1" in
		--fork) fork="$2" ;;
		--upstream) upstream="$2" ;;
		esac
		shift 2
		;;
	-h | --help)
		sed -n '2,18p' "$0"
		exit 0
		;;
	*)
		echo "unknown argument: $1" >&2
		exit 2
		;;
	esac
done

command -v gh >/dev/null 2>&1 || {
	echo "gh is required" >&2
	exit 2
}

head_of() { gh api "repos/$1/git/ref/heads/main" --jq .object.sha; }

fork_sha="$(head_of "$fork")"
up_sha="$(head_of "$upstream")"

# base=fork main, head=upstream main: "identical" or "behind" means fork main
# already contains upstream main; "ahead" or "diverged" means upstream has
# commits fork main lacks.
rel="$(gh api "repos/$fork/compare/main...${upstream%%/*}:main" --jq .status)"
case "$rel" in
identical | behind)
	echo "fork main already contains upstream main (${up_sha:0:10}); status: $rel"
	exit 0
	;;
esac

tag="backup/fork-main-$(date -u +%Y%m%d%H%M%S)"
gh api "repos/$fork/git/refs" -f ref="refs/tags/$tag" -f sha="$fork_sha" --jq '"backup: " + .ref' >&2

if ! gh api -X POST "repos/$fork/merge-upstream" -f branch=main --jq .message >&2; then
	echo "merge-upstream failed. A 409 means upstream conflicts with the carry files; main is unchanged." >&2
	echo "Resolve by hand (merge upstream into a branch off main, fix the carry files, land it). Backup tag: $tag" >&2
	exit 1
fi

after="$(head_of "$fork")"
# Main must now contain upstream's pre-sync tip: compare that SHA against main.
contained="$(gh api "repos/$fork/compare/$up_sha...main" --jq .status)"
case "$contained" in
identical | ahead) ;;
*)
	echo "main is ${after:0:10} but does not contain upstream ${up_sha:0:10} (status: $contained)" >&2
	exit 1
	;;
esac
echo "main = ${after:0:10} (was ${fork_sha:0:10}); contains upstream ${up_sha:0:10}; backup tag $tag"
