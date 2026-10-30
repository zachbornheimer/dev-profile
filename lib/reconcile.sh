#!/usr/bin/env bash
set -euo pipefail
# Edit lib/reconcile.sh: `mise run generate` copies it into bin/.

# Rebase the current branch onto GitHub's copy and push the result. On a
# conflict, stop mid-rebase in this worktree for a person to resolve.
branch="$(git symbolic-ref --quiet --short HEAD)" || {
	echo "Detached HEAD; check out the branch to reconcile" >&2
	exit 1
}
git fetch --quiet origin
if ! git rev-parse --verify --quiet "refs/remotes/origin/${branch}" >/dev/null; then
	echo "origin/${branch} does not exist; nothing to reconcile. Publish it with: wt sync"
	exit 0
fi
if ! git rebase "origin/${branch}"; then
	echo "Resolve the conflicts in $(pwd), then: git rebase --continue && wt sync" >&2
	exit 1
fi
git push origin "HEAD:refs/heads/${branch}"
echo "Reconciled ${branch} with GitHub"
