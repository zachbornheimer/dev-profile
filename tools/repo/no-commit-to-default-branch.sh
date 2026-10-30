#!/usr/bin/env bash
set -euo pipefail
# Edit tools/repo/no-commit-to-default-branch.sh: `mise run generate` copies it into bin/.

# Refuse a direct commit on main or master, except where that is the normal way
# work lands: finishing a merge, cherry-pick, revert, or rebase; a repo with no
# origin (nothing to publish a branch to); or an explicit opt-out.
[[ -z "${DEV_PROFILE_ALLOW_DEFAULT_BRANCH_COMMIT:-}" ]] || exit 0
for operation in MERGE_HEAD CHERRY_PICK_HEAD REVERT_HEAD rebase-merge rebase-apply; do
	if [[ -e "$(git rev-parse --git-path "${operation}")" ]]; then exit 0; fi
done
git remote get-url origin >/dev/null 2>&1 || exit 0
if ! hk util no-commit-to-branch; then
	echo "Commit on a feature branch (wt switch -c <branch>), or set DEV_PROFILE_ALLOW_DEFAULT_BRANCH_COMMIT=1." >&2
	exit 1
fi
