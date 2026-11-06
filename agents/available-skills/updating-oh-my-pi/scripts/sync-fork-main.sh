#!/usr/bin/env bash
# sync-fork-main.sh: fast-forward the fork's main to upstream main.
#
# The fork's `main` is an exact mirror of can1357/oh-my-pi:main, and the
# `main-mirrors-upstream` ruleset blocks every update to it (update, deletion,
# non_fast_forward), including GitHub's own sync. This script opens a repo-admin
# bypass for the length of one merge-upstream call and restores the ruleset's
# previous bypass list on every exit path (a trap), so protection is back on
# whether the sync succeeds or not.
#
# Safety: refuses when fork main holds commits upstream lacks (diverged), and
# records a backup tag `backup/fork-main-<UTC>` on the fork before moving main.
# merge-upstream only ever fast-forwards, so nothing on main can be lost.
#
# Usage: sync-fork-main.sh [--fork OWNER/REPO] [--upstream OWNER/REPO]
# Exit: 0 main equals upstream main afterwards; 1 refused or sync failed;
# 2 usage or API error.
set -euo pipefail

fork="${OMP_FORK:-zachbornheimer/oh-my-pi}"
upstream="${OMP_UPSTREAM:-can1357/oh-my-pi}"
ruleset_name="main-mirrors-upstream"
admin_role_id=5 # GitHub's built-in repository Admin role

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
		sed -n '2,17p' "$0"
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
if [ "$fork_sha" = "$up_sha" ]; then
	echo "already in sync: main = ${up_sha:0:10}"
	exit 0
fi

# base=fork main, head=upstream main: "ahead" means upstream only adds commits.
# "diverged" means fork main holds commits upstream lacks: not a mirror.
rel="$(gh api "repos/$fork/compare/main...${upstream%%/*}:main" --jq .status)"
if [ "$rel" != "ahead" ]; then
	echo "REFUSED: fork main is '$rel' relative to upstream main, not a pure ancestor." >&2
	echo "Move any fork-only commits on main to a topic branch first." >&2
	exit 1
fi

ruleset_id="$(gh api "repos/$fork/rulesets" --jq ".[] | select(.name == \"$ruleset_name\") | .id")"
[ -n "$ruleset_id" ] || {
	echo "ruleset '$ruleset_name' not found on $fork" >&2
	exit 2
}
ruleset="repos/$fork/rulesets/$ruleset_id"
original="$(gh api "$ruleset" --jq '{bypass_actors: .bypass_actors}')"

tag="backup/fork-main-$(date -u +%Y%m%d%H%M%S)"
gh api "repos/$fork/git/refs" -f ref="refs/tags/$tag" -f sha="$fork_sha" --jq '"backup: " + .ref' >&2

restore() {
	if printf '%s' "$original" | gh api -X PUT "$ruleset" --input - --jq '"bypass restored: \(.bypass_actors | length) actor(s)"' >&2; then
		:
	else
		echo "!! FAILED to restore the ruleset bypass; restore it by hand: PUT $ruleset with $original" >&2
	fi
}
trap restore EXIT

printf '{"bypass_actors":[{"actor_id":%s,"actor_type":"RepositoryRole","bypass_mode":"always"}]}' "$admin_role_id" |
	gh api -X PUT "$ruleset" --input - --jq '"bypass opened for sync"' >&2

gh api -X POST "repos/$fork/merge-upstream" -f branch=main --jq .message >&2

after="$(head_of "$fork")"
if [ "$after" != "$up_sha" ]; then
	echo "main is ${after:0:10}, expected ${up_sha:0:10}" >&2
	exit 1
fi
echo "main = ${after:0:10} (was ${fork_sha:0:10}); backup tag $tag"
