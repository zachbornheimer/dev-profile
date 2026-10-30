# shellcheck shell=bash
# Sourced by the profile's bin/ scripts: Facts about the clone the sync and retire scripts share.
# Edit lib/sh/repo-facts.sh: `mise run generate` copies it into lib/.

# Only origin: another remote that fails must not stop this. PR heads land in
# refs/sync/pull, out of `git branch -r`, so work GitHub holds only as a PR counts.
git fetch --prune --quiet origin '+refs/heads/*:refs/remotes/origin/*' '+refs/pull/*/head:refs/sync/pull/*'
git symbolic-ref --quiet refs/remotes/origin/HEAD >/dev/null ||
	git remote set-head origin --auto >/dev/null 2>&1 || true
default_branch="$(git symbolic-ref --quiet --short refs/remotes/origin/HEAD 2>/dev/null || :)"
default_branch="${default_branch#origin/}"
default_branch="${default_branch:-main}"
base="refs/remotes/origin/${default_branch}"
# Read by the scripts that source this file.
export base

# True when a branch or PR head on origin already contains commit $1.
on_github() {
	[[ -n "$(git for-each-ref --contains "$1" --count=1 refs/remotes/origin refs/sync/pull)" ]]
}

# True when merging $1 into $2 would change nothing: an ancestor, or content
# already there (a squash merge, or a rebase that $2 went through).
adds_nothing() {
	git merge-base --is-ancestor "$1" "$2" && return 0
	local tree
	tree="$(git merge-tree --write-tree "$2" "$1" 2>/dev/null | sed -n 1p)" || return 1
	[[ "${tree}" == "$(git rev-parse "$2^{tree}")" ]]
}

# Worktrees, the primary first, one per line as fields split by ${sep} (empty
# fields survive, unlike tabs): path, branch (empty when detached), HEAD, and
# "locked" or empty.
sep=$'\037'
worktrees() {
	git worktree list --porcelain | awk -v OFS="${sep}" '
    function emit() { if (path != "") print path, branch, head, locked }
    /^worktree / { emit(); path = substr($0, 10); branch = ""; head = ""; locked = "" }
    /^HEAD / { head = substr($0, 6) }
    /^branch refs\/heads\// { branch = substr($0, 19) }
    /^locked/ { locked = "locked" }
    END { emit() }'
}

# The worktree line for branch $1, if it has one.
worktree_of() { worktrees | awk -F "${sep}" -v b="$1" '$2 == b && !found { print; found = 1 }'; }
