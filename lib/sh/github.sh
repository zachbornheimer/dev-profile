# shellcheck shell=bash
# Sourced by the profile's bin/ scripts: gh-scope.sh plus `owner`, `default_branch` and `branch_prs <branch> <state>`.
# Edit lib/sh/github.sh: `mise run generate` copies it into lib/.

command -v gh >/dev/null || {
	echo "GitHub CLI (gh) is required" >&2
	exit 1
}
# shellcheck source=lib/sh/gh-scope.sh
source "$(dirname "${BASH_SOURCE[0]}")/gh-scope.sh"
repo_json="$(gh repo view ${slug:+"${slug}"} --json owner,defaultBranchRef)"
owner="$(jq -r .owner.login <<<"${repo_json}")"
default_branch="$(jq -r .defaultBranchRef.name <<<"${repo_json}")"
# Read by the scripts that source this file.
export default_branch

# This repo's own PRs (not forks') for branch $1 in state $2, newest first.
branch_prs() {
	ghr pr list --head "$1" --state "$2" \
		--json number,url,state,isDraft,headRefOid,headRepositoryOwner \
		--jq "[.[] | select(.headRepositoryOwner.login == \"${owner}\")]"
}
