# shellcheck shell=bash
# Sourced by the profile's bin/ scripts: `remove_merged <branch> <merged-oid>`.
# Edit lib/sh/remove-merged.sh: `mise run generate` copies it into lib/.

# Remove branch $1 and its worktree, given $2: the head commit GitHub merged.
# Force-deletes only when the local tip is exactly that commit, so work made
# after the merge survives. A dirty worktree makes wt refuse; that is kept.
remove_merged() {
	if [[ "$(git rev-parse --verify --quiet "refs/heads/$1")" == "$2" ]]; then
		wt remove --foreground --force-delete "$1"
	else
		wt remove --foreground "$1"
	fi
}
